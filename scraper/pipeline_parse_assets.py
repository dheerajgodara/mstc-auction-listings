"""Fast Parse lane: wave prefetch → ProcessPool PyMuPDF → batch Hostinger flush."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import (
    DEFAULT_PARSED_DIR,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    PARSE_FAIL_BUDGET_ABS,
    PARSE_FAIL_BUDGET_PCT,
    PARSE_WAVE_SIZE,
    PARSE_WORKERS,
    PARSER_CACHE_VERSION,
    PIPELINE_JOB_TIMEBOX_MIN,
    REPO_ROOT,
)
from scraper.filters import make_run_id
from scraper.lane_resume import dispatch_workflow, record_resume, should_self_resume
from scraper.media_sync import media_push_required
from scraper.models import AuctionRecord
from scraper.parse_cache import (
    build_parse_artifact,
    file_sha256,
    is_fresh_parse,
    load_parse_artifact,
    local_parsed_path,
    write_parse_artifact,
)
from scraper.parse_engine import worker_parse_mstc
from scraper.parse_flush import flush_parsed_files
from scraper.parse_journal import ParseJournal
from scraper.pipeline_ledger import (
    fail_budget_ok,
    load_ledger,
    mark_parse,
    pull_ledger,
    push_ledger,
    select_for_parse,
    write_ledger,
)
from scraper.raw_store import (
    _hostinger_ssh_config,
    pull_public_pdf_files,
    pull_public_relative_files,
    pull_raw_files,
)
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_parse_assets")


def _phase(msg: str) -> None:
    print(f"[parse_assets] {msg}", flush=True)
    logger.info(msg)


def _parse_id_set(raw: str | None) -> set[str] | None:
    if not raw or not str(raw).strip():
        return None
    ids = {p.strip() for p in str(raw).split(",") if p.strip()}
    return ids or None


def _worker_count() -> int:
    n = int(PARSE_WORKERS or 0)
    if n > 0:
        return max(1, n)
    cpu = os.cpu_count() or 2
    return max(1, cpu - 1)


def _prefetch_wave(
    wave: list[Any],
    *,
    public_dir: Path,
    pdf_dir: Path,
    raw_dir: Path,
) -> None:
    mstc = [i for i in wave if i.source == "mstc"]
    gem = [i for i in wave if i.source == "gem_forward"]
    if mstc:
        pairs = [(i.source, str(i.source_auction_id)) for i in mstc]
        pull_raw_files(pairs, raw_dir=raw_dir, timeout_sec=300)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        names = []
        for i in mstc:
            host_rel = (i.hostinger_doc_path or f"pdfs/{i.source_auction_id}.pdf").lstrip("/")
            names.append(Path(host_rel).name)
            # Skip pull if local PDF already matches sha
            local = public_dir / host_rel
            if not local.is_file():
                local = pdf_dir / f"{i.source_auction_id}.pdf"
            if local.is_file() and i.doc_sha256:
                try:
                    if file_sha256(local) == i.doc_sha256:
                        continue
                except Exception:
                    pass
            names.append(Path(host_rel).name)
        pull_public_pdf_files(public_dir=public_dir, filenames=sorted(set(names)))
    if gem:
        rels = [(i.hostinger_doc_path or "").lstrip("/") for i in gem if (i.hostinger_doc_path or "").strip()]
        if rels:
            pull_public_relative_files(public_dir=public_dir, relative_paths=rels)


def _build_mstc_spec(
    item: Any,
    *,
    public_dir: Path,
    pdf_dir: Path,
    raw_dir: Path,
) -> dict[str, Any] | None:
    aid = str(item.source_auction_id)
    host_rel = (item.hostinger_doc_path or f"pdfs/{aid}.pdf").lstrip("/")
    local = public_dir / host_rel
    if not local.is_file():
        local = pdf_dir / f"{aid}.pdf"
    if not local.is_file():
        return None
    raw_path = raw_dir / "mstc" / f"{aid}.html"
    return {
        "stable_key": item.stable_key,
        "source_auction_id": aid,
        "pdf_path": str(local),
        "raw_html_path": str(raw_path) if raw_path.is_file() else None,
        "hostinger_doc_path": item.hostinger_doc_path,
        "hostinger_doc_url": item.hostinger_doc_url,
        "portal_doc_url": item.portal_doc_url,
        "doc_sha256": item.doc_sha256 or (file_sha256(local) if local.is_file() else None),
        "auction_number": getattr(item, "auction_number", None) or aid,
        "region": getattr(item, "region", None) or "",
        "office": getattr(item, "office", None) or "",
        "state": getattr(item, "state", None),
        "seller": getattr(item, "seller", None),
        "detail_url": getattr(item, "detail_url", None),
        "opening": getattr(item, "opening", None),
        "closing": getattr(item, "closing", None),
    }


def _enrich_gem_wave(wave: list[Any]) -> dict[str, dict[str, Any]]:
    ids = {str(i.source_auction_id) for i in wave if i.source == "gem_forward"}
    if not ids:
        return {}
    from scraper.pipeline_parse import _enrich_non_mstc_batch

    batch = _enrich_non_mstc_batch("gem_forward", ids)
    out: dict[str, dict[str, Any]] = {}
    for aid, record in batch.items():
        if isinstance(record, AuctionRecord):
            out[str(aid)] = record.model_dump(mode="json")
        elif isinstance(record, dict):
            out[str(aid)] = dict(record)
    return out


def run_parse_assets(
    *,
    repo_root: Path = REPO_ROOT,
    timebox_min: int = PIPELINE_JOB_TIMEBOX_MIN,
    break_stale_lock: bool = True,
    max_parse: int | None = None,
    auction_ids: str | None = None,
    wave_size: int = PARSE_WAVE_SIZE,
) -> dict[str, Any]:
    run_id = f"parse_assets_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(run_dir / "parse_assets.log", encoding="utf-8"),
        ],
        force=True,
    )

    lock_path = repo_root / "work" / "parse_assets.lock"
    acquire_refresh_lock(
        lock_path=lock_path, run_id=run_id, stale_minutes=360, break_stale_lock=break_stale_lock
    )

    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    pdf_dir = Path(DEFAULT_PDF_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    parsed_root = Path(DEFAULT_PARSED_DIR)
    public_dir = repo_root / "web" / "public"
    journal = ParseJournal(run_dir / "parse_journal.jsonl")
    t0 = time.monotonic()
    parsed_n = skipped = failed = 0
    capped_run = max_parse is not None and int(max_parse) > 0
    id_filter = _parse_id_set(auction_ids)
    attempted_ids: list[str] = []
    wave_size = max(1, int(wave_size))
    workers = _worker_count()
    timing = {"prefetch_s": 0.0, "cpu_s": 0.0, "flush_s": 0.0}

    try:
        if media_push_required() and _hostinger_ssh_config() is None:
            raise RuntimeError(
                "parse requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1"
            )

        pulled = pull_ledger(local_path=ledger_path)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError("ledger pull failed and local ledger is empty — refusing parse")

        queue = select_for_parse(ledger, limit=None)
        if id_filter is not None:
            queue = [i for i in queue if str(i.source_auction_id) in id_filter]
            if not queue:
                queue = [
                    i
                    for i in ledger.items
                    if str(i.source_auction_id) in id_filter
                    and i.download == "done"
                    and (i.hostinger_doc_url or "").strip()
                    and (i.hostinger_doc_path or "").strip()
                    and not i.removed_from_source
                ]
                for item in queue:
                    if item.parse == "done":
                        item.parse = "pending"
                        item.parse_error = None
            _phase(f"auction_ids filter={sorted(id_filter)} matched={len(queue)}")
        if capped_run:
            queue = queue[: int(max_parse)]
        _phase(f"queue={len(queue)} wave_size={wave_size} workers={workers}")

        offset = 0
        wave_num = 0
        while offset < len(queue):
            elapsed_min = (time.monotonic() - t0) / 60.0
            if elapsed_min >= timebox_min:
                _phase("timebox reached")
                break

            wave = queue[offset : offset + wave_size]
            offset += len(wave)
            wave_num += 1
            _phase(f"wave {wave_num}: selected={len(wave)}")

            tp = time.perf_counter()
            _prefetch_wave(wave, public_dir=public_dir, pdf_dir=pdf_dir, raw_dir=raw_dir)
            timing["prefetch_s"] += time.perf_counter() - tp

            # Pending successes: mark_parse(done) only AFTER Hostinger flush succeeds.
            pending_ok: list[dict[str, Any]] = []
            wave_flush: list[Path] = []

            # Fresh skips (local only — flush later if needed)
            work_specs: list[dict[str, Any]] = []
            gem_items: list[Any] = []
            for item in wave:
                if not (item.hostinger_doc_url or "").strip() or not (
                    item.hostinger_doc_path or ""
                ).strip():
                    mark_parse(
                        ledger,
                        item.stable_key,
                        ok=False,
                        error="missing hostinger_doc_url — download required",
                        durability_failed=True,
                    )
                    failed += 1
                    continue
                out_path = local_parsed_path(item.source, item.source_auction_id, root=parsed_root)
                host_rel = (item.hostinger_doc_path or "").lstrip("/")
                local_doc = public_dir / host_rel if host_rel else None
                if item.source == "mstc" and (local_doc is None or not local_doc.is_file()):
                    local_doc = pdf_dir / f"{item.source_auction_id}.pdf"
                pdf_hash = (
                    file_sha256(local_doc)
                    if local_doc is not None and local_doc.is_file()
                    else (item.doc_sha256 or None)
                )
                existing = load_parse_artifact(out_path)
                if is_fresh_parse(
                    existing, pdf_sha256=pdf_hash, parser_version=PARSER_CACHE_VERSION
                ):
                    lots = (existing or {}).get("record", {}).get("lots") or []
                    n_lots = len(lots) if isinstance(lots, list) else 0
                    if n_lots > 0:
                        pending_ok.append(
                            {
                                "stable_key": item.stable_key,
                                "lots_count": n_lots,
                                "parsed_path": f"parsed/{item.source}/{item.source_auction_id}.json",
                                "doc_sha256": pdf_hash,
                                "fresh": True,
                            }
                        )
                        wave_flush.append(out_path)
                        journal.append(
                            {
                                "stable_key": item.stable_key,
                                "ok": True,
                                "lots": n_lots,
                                "fresh": True,
                            }
                        )
                        skipped += 1
                        attempted_ids.append(str(item.source_auction_id))
                        continue

                if item.source == "gem_forward":
                    gem_items.append(item)
                    continue

                spec = _build_mstc_spec(
                    item, public_dir=public_dir, pdf_dir=pdf_dir, raw_dir=raw_dir
                )
                if spec is None:
                    mark_parse(
                        ledger,
                        item.stable_key,
                        ok=False,
                        error="PDF missing locally for parse",
                        durability_failed=True,
                    )
                    failed += 1
                    continue
                work_specs.append(spec)
                attempted_ids.append(str(item.source_auction_id))

            # GeM: one enrich for the whole wave
            if gem_items:
                tg = time.perf_counter()
                gem_map = _enrich_gem_wave(gem_items)
                timing["cpu_s"] += time.perf_counter() - tg
                for item in gem_items:
                    aid = str(item.source_auction_id)
                    attempted_ids.append(aid)
                    rec = gem_map.get(aid)
                    if not rec:
                        mark_parse(
                            ledger,
                            item.stable_key,
                            ok=False,
                            error="gem enrich returned nothing",
                        )
                        failed += 1
                        journal.append(
                            {"stable_key": item.stable_key, "ok": False, "error": "gem empty"}
                        )
                        continue
                    rec = dict(rec)
                    rec["pdf_url"] = item.hostinger_doc_path
                    rec["hostinger_doc_url"] = item.hostinger_doc_url
                    rec["source_pdf_url"] = item.portal_doc_url
                    lots = rec.get("lots") or []
                    n_lots = len(lots) if isinstance(lots, list) else 0
                    out_path = local_parsed_path(item.source, aid, root=parsed_root)
                    if n_lots > 0:
                        artifact = build_parse_artifact(
                            record=rec,
                            stable_key=item.stable_key,
                            pdf_sha256=item.doc_sha256,
                            parser_version=PARSER_CACHE_VERSION,
                        )
                        write_parse_artifact(out_path, artifact)
                        wave_flush.append(out_path)
                        pending_ok.append(
                            {
                                "stable_key": item.stable_key,
                                "lots_count": n_lots,
                                "parsed_path": f"parsed/{item.source}/{aid}.json",
                                "doc_sha256": item.doc_sha256,
                            }
                        )
                        journal.append(
                            {"stable_key": item.stable_key, "ok": True, "lots": n_lots}
                        )
                    else:
                        mark_parse(
                            ledger,
                            item.stable_key,
                            ok=False,
                            error="no lots",
                        )
                        failed += 1
                        journal.append(
                            {"stable_key": item.stable_key, "ok": False, "lots": 0}
                        )

            # MSTC parallel CPU
            if work_specs:
                tc = time.perf_counter()
                with ProcessPoolExecutor(max_workers=min(workers, len(work_specs))) as pool:
                    futs = {pool.submit(worker_parse_mstc, spec): spec for spec in work_specs}
                    for fut in as_completed(futs):
                        result = fut.result()
                        key = result["stable_key"]
                        aid = result["source_auction_id"]
                        if result.get("ok") and result.get("record"):
                            out_path = local_parsed_path("mstc", aid, root=parsed_root)
                            artifact = build_parse_artifact(
                                record=result["record"],
                                stable_key=key,
                                pdf_sha256=result.get("doc_sha256"),
                                parser_version=PARSER_CACHE_VERSION,
                            )
                            write_parse_artifact(out_path, artifact)
                            wave_flush.append(out_path)
                            pending_ok.append(
                                {
                                    "stable_key": key,
                                    "lots_count": int(result.get("lots_count") or 0),
                                    "parsed_path": f"parsed/mstc/{aid}.json",
                                    "doc_sha256": result.get("doc_sha256"),
                                    "engine": result.get("engine"),
                                    "parse_ms": result.get("parse_ms"),
                                }
                            )
                            journal.append(
                                {
                                    "stable_key": key,
                                    "ok": True,
                                    "lots": result.get("lots_count"),
                                    "engine": result.get("engine"),
                                    "parse_ms": result.get("parse_ms"),
                                }
                            )
                            _phase(
                                f"parse_item source=mstc id={aid} ok=True "
                                f"lots={result.get('lots_count')} "
                                f"engine={result.get('engine')} ms={result.get('parse_ms')}"
                            )
                        else:
                            mark_parse(
                                ledger,
                                key,
                                ok=False,
                                error=result.get("error") or "parse failed",
                                durability_failed="missing" in str(result.get("error") or "").lower()
                                or "PDF" in str(result.get("error") or ""),
                            )
                            failed += 1
                            journal.append(
                                {
                                    "stable_key": key,
                                    "ok": False,
                                    "error": result.get("error"),
                                    "parse_ms": result.get("parse_ms"),
                                }
                            )
                            _phase(
                                f"parse_item source=mstc id={aid} ok=False "
                                f"error={result.get('error')}"
                            )
                timing["cpu_s"] += time.perf_counter() - tc

            # Flush then mark done (reliability: no done without Hostinger when required)
            if wave_flush and media_push_required():
                tf = time.perf_counter()
                unique = sorted(set(wave_flush), key=str)
                ok, msg = flush_parsed_files(unique, parsed_root=parsed_root)
                timing["flush_s"] += time.perf_counter() - tf
                _phase(f"wave flush: {msg}")
                if not ok:
                    raise RuntimeError(f"Hostinger parse flush failed: {msg}")
                journal.append({"event": "wave_flushed", "wave": wave_num, "ok": True})
            elif wave_flush and not media_push_required():
                _phase(f"wave flush skipped (MEDIA_PUSH_REQUIRED=0) files={len(wave_flush)}")

            for row in pending_ok:
                mark_parse(
                    ledger,
                    row["stable_key"],
                    ok=True,
                    lots_count=int(row["lots_count"]),
                    parsed_path=row["parsed_path"],
                    parser_version=PARSER_CACHE_VERSION,
                )
                it = ledger.by_key().get(row["stable_key"])
                if it and row.get("doc_sha256"):
                    it.doc_sha256 = row["doc_sha256"]
                if not row.get("fresh"):
                    parsed_n += 1

            write_ledger(ledger, ledger_path)
            push_ledger(local_path=ledger_path)

            elapsed = time.monotonic() - t0
            rate = (parsed_n + skipped) / elapsed if elapsed > 0 else 0
            _phase(
                f"wave {wave_num} done parsed={parsed_n} skipped={skipped} failed={failed} "
                f"rate={rate:.2f}/s"
            )

        backlog = len(select_for_parse(load_ledger(ledger_path), limit=None))
        attempted = parsed_n + failed
        budget_ok = fail_budget_ok(
            failed=failed,
            attempted=max(1, attempted),
            pct=PARSE_FAIL_BUDGET_PCT,
            absolute=PARSE_FAIL_BUDGET_ABS,
        )
        elapsed_min = (time.monotonic() - t0) / 60.0
        resume = False
        reason = "capped_or_filtered" if (capped_run or id_filter is not None) else ""
        if not capped_run and id_filter is None:
            resume, reason = should_self_resume(
                backlog_left=backlog,
                failed=failed,
                attempted=attempted,
                fail_budget_ok=budget_ok,
                elapsed_min=elapsed_min,
                timebox_min=timebox_min,
            )
            if resume:
                record_resume("parse", {"reason": reason, "backlog_left": backlog})
                dispatch_workflow("pipeline-parse-assets.yml")

        elapsed = time.monotonic() - t0
        status = "Complete" if backlog == 0 else "Paused · timebox"
        send_lane_report(
            "parse",
            "finished",
            {
                "status": status,
                "parsed": parsed_n,
                "skipped_fresh": skipped,
                "failed": failed,
                "backlog_left": backlog,
                "resume_next": resume,
                "items_per_sec": round((parsed_n + skipped) / elapsed, 3) if elapsed else 0,
            },
            noop=attempted == 0 and skipped == 0 and backlog == 0,
        )
        payload = {
            "run_id": run_id,
            "parsed": parsed_n,
            "skipped": skipped,
            "failed": failed,
            "attempted_ids": attempted_ids,
            "max_parse": max_parse,
            "auction_ids": sorted(id_filter) if id_filter else None,
            "backlog_left": backlog,
            "resume": resume,
            "resume_reason": reason,
            "workers": workers,
            "wave_size": wave_size,
            "timing": timing,
            "elapsed_s": round(elapsed, 2),
            "items_per_sec": round((parsed_n + skipped) / elapsed, 3) if elapsed else 0,
        }
        if attempted_ids:
            _phase(f"attempted_ids={','.join(attempted_ids[:50])}{'…' if len(attempted_ids)>50 else ''}")
        _phase(
            f"done parsed={parsed_n} skipped={skipped} failed={failed} "
            f"elapsed={elapsed:.1f}s rate={payload['items_per_sec']}/s "
            f"timing={timing}"
        )
        (run_dir / "parse_assets_report.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return payload
    except Exception as exc:
        send_lane_report("parse", "failed", {"error": str(exc), "backlog_left": "?"})
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fast parse assets lane (wave + process pool)")
    parser.add_argument("--timebox-min", type=int, default=PIPELINE_JOB_TIMEBOX_MIN)
    parser.add_argument("--max-parse", type=int, default=None)
    parser.add_argument("--wave-size", type=int, default=PARSE_WAVE_SIZE)
    parser.add_argument(
        "--auction-ids",
        default=None,
        help="Comma-separated source_auction_id filter (smoke / targeted parse)",
    )
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_parse_assets(
        timebox_min=args.timebox_min,
        break_stale_lock=args.break_stale_lock,
        max_parse=args.max_parse,
        auction_ids=args.auction_ids,
        wave_size=args.wave_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
