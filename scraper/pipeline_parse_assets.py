"""Independent Parse lane: one-by-one parse → Hostinger save → verify → next."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from scraper.config import (
    DEFAULT_PARSED_DIR,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    PARSE_BATCH_RETRY_ROUNDS,
    PARSE_BATCH_SIZE,
    PARSE_FAIL_BUDGET_ABS,
    PARSE_FAIL_BUDGET_PCT,
    PARSE_SUCCESS_PAUSE_SEC,
    PARSER_CACHE_VERSION,
    PIPELINE_JOB_TIMEBOX_MIN,
    REPO_ROOT,
)
from scraper.filters import make_run_id
from scraper.lane_resume import dispatch_workflow, record_resume, should_self_resume
from scraper.main import enrich_auction, resolve_auction_listing
from scraper.media_sync import media_push_required
from scraper.models import AuctionRecord
from scraper.parse_cache import (
    build_parse_artifact,
    file_sha256,
    is_fresh_parse,
    load_parse_artifact,
    local_parsed_path,
    pull_parsed_tree,
    push_and_verify_parsed_file,
    verify_parsed_file,
    write_parse_artifact,
)
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

ParseOutcome = Literal["done", "skipped", "no_lots", "durability", "error"]


def _phase(msg: str) -> None:
    print(f"[parse_assets] {msg}", flush=True)
    logger.info(msg)


def _parse_id_set(raw: str | None) -> set[str] | None:
    if not raw or not str(raw).strip():
        return None
    ids = {p.strip() for p in str(raw).split(",") if p.strip()}
    return ids or None


def _pause_between_auctions() -> None:
    time.sleep(max(0.0, PARSE_SUCCESS_PAUSE_SEC))


def _pull_item_docs(
    *,
    item: Any,
    public_dir: Path,
    pdf_dir: Path,
    raw_dir: Path,
) -> Path | None:
    """Pull this auction's Hostinger doc (+ raw for MSTC). Returns local doc path if present."""
    aid = str(item.source_auction_id)
    host_rel = (item.hostinger_doc_path or f"pdfs/{aid}.pdf").lstrip("/")
    if item.source == "mstc":
        pull_raw_files([(item.source, aid)], raw_dir=raw_dir, timeout_sec=120)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pull_public_pdf_files(
            public_dir=public_dir,
            filenames=[Path(host_rel).name],
        )
    else:
        pull_public_relative_files(public_dir=public_dir, relative_paths=[host_rel])

    local_doc = public_dir / host_rel
    if item.source == "mstc" and not local_doc.is_file():
        local_doc = pdf_dir / f"{aid}.pdf"
    return local_doc if local_doc.is_file() else None


def _parse_record(item: Any, *, pdf_dir: Path, raw_dir: Path, local_doc: Path) -> dict[str, Any]:
    aid = str(item.source_auction_id)
    src = item.source
    if src == "mstc":
        if not local_doc.is_file():
            raise FileNotFoundError(f"Hostinger PDF missing locally for parse: {local_doc}")
        base, _meta = resolve_auction_listing(aid)
        record = enrich_auction(
            base,
            pdf_dir=pdf_dir,
            skip_pdf=False,
            stats={},
            mode="parse_only",
            raw_dir=raw_dir,
        )
        return record.model_dump(mode="json")

    from scraper.pipeline_parse import _enrich_non_mstc_batch

    batch = _enrich_non_mstc_batch("gem_forward", {aid})
    record = batch.get(aid)
    if record is None:
        raise RuntimeError(f"gem enrich returned nothing for {aid}")
    if isinstance(record, AuctionRecord):
        return record.model_dump(mode="json")
    return dict(record)


def _durable_save(
    *,
    out_path: Path,
    artifact: dict[str, Any],
    source: str,
    aid: str,
) -> None:
    """Write local + push Hostinger + verify. Raises on durability failure when required."""
    write_parse_artifact(out_path, artifact)
    expected = file_sha256(out_path)
    if media_push_required():
        if _hostinger_ssh_config() is None:
            raise RuntimeError("parse requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1")
        if not push_and_verify_parsed_file(out_path, source=source, source_auction_id=aid):
            raise RuntimeError(f"Hostinger parse artifact push/verify failed for {source}/{aid}")
    else:
        # Local-only mode (tests): still require local write succeeded.
        if not out_path.is_file() or file_sha256(out_path) != expected:
            raise RuntimeError(f"local parse artifact incomplete for {source}/{aid}")


def _process_one(
    *,
    item: Any,
    ledger: Any,
    ledger_path: Path,
    public_dir: Path,
    pdf_dir: Path,
    raw_dir: Path,
    parsed_root: Path,
) -> ParseOutcome:
    """Parse → save → verify once. Returns outcome kind for retry classification."""
    aid = str(item.source_auction_id)
    src = item.source
    parsed_rel = f"parsed/{src}/{aid}"

    if not (item.hostinger_doc_url or "").strip() or not (item.hostinger_doc_path or "").strip():
        mark_parse(
            ledger,
            item.stable_key,
            ok=False,
            error="missing hostinger_doc_url — download required",
            durability_failed=True,
        )
        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)
        return "durability"

    local_doc = _pull_item_docs(item=item, public_dir=public_dir, pdf_dir=pdf_dir, raw_dir=raw_dir)
    out_path = local_parsed_path(src, aid, root=parsed_root)
    pdf_hash = (
        file_sha256(local_doc)
        if local_doc is not None and local_doc.is_file()
        else (item.doc_sha256 or None)
    )

    # Fresh local cache: skip reparse only if Hostinger still has matching artifact.
    existing = load_parse_artifact(out_path)
    if is_fresh_parse(existing, pdf_sha256=pdf_hash, parser_version=PARSER_CACHE_VERSION):
        lots = (existing or {}).get("record", {}).get("lots") or []
        n_lots = len(lots) if isinstance(lots, list) else 0
        if n_lots > 0:
            durable_ok = True
            if media_push_required():
                durable_ok = verify_parsed_file(
                    src, aid, expected_sha256=file_sha256(out_path)
                )
                if not durable_ok:
                    # Re-push existing local artifact; do not reparse.
                    try:
                        _durable_save(
                            out_path=out_path,
                            artifact=existing or {},
                            source=src,
                            aid=aid,
                        )
                        durable_ok = True
                    except Exception as exc:
                        mark_parse(
                            ledger,
                            item.stable_key,
                            ok=False,
                            error=str(exc),
                            durability_failed=True,
                        )
                        write_ledger(ledger, ledger_path)
                        push_ledger(local_path=ledger_path)
                        return "durability"
            if durable_ok:
                mark_parse(
                    ledger,
                    item.stable_key,
                    ok=True,
                    lots_count=n_lots,
                    parsed_path=f"{parsed_rel}.json",
                    parser_version=PARSER_CACHE_VERSION,
                )
                it = ledger.by_key().get(item.stable_key)
                if it and pdf_hash:
                    it.doc_sha256 = pdf_hash
                write_ledger(ledger, ledger_path)
                push_ledger(local_path=ledger_path)
                _phase(f"parse_item source={src} id={aid} ok=True lots={n_lots} fresh=1")
                return "skipped"

    if local_doc is None or not local_doc.is_file():
        mark_parse(
            ledger,
            item.stable_key,
            ok=False,
            error=f"Hostinger PDF missing locally for parse: {item.hostinger_doc_path}",
            durability_failed=True,
        )
        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)
        return "durability"

    try:
        rec = _parse_record(item, pdf_dir=pdf_dir, raw_dir=raw_dir, local_doc=local_doc)
        lots = rec.get("lots") or []
        n_lots = len(lots) if isinstance(lots, list) else 0
        rec["pdf_url"] = item.hostinger_doc_path
        rec["hostinger_doc_url"] = item.hostinger_doc_url
        rec["source_pdf_url"] = item.portal_doc_url
        artifact = build_parse_artifact(
            record=rec,
            stable_key=item.stable_key,
            pdf_sha256=pdf_hash,
            parser_version=PARSER_CACHE_VERSION,
        )
        _durable_save(out_path=out_path, artifact=artifact, source=src, aid=aid)
        ok = n_lots > 0
        mark_parse(
            ledger,
            item.stable_key,
            ok=ok,
            lots_count=n_lots,
            parsed_path=f"{parsed_rel}.json" if ok else None,
            error=None if ok else "no lots",
            parser_version=PARSER_CACHE_VERSION if ok else None,
            durability_failed=False,
        )
        it = ledger.by_key().get(item.stable_key)
        if it and pdf_hash:
            it.doc_sha256 = pdf_hash
        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)
        _phase(f"parse_item source={src} id={aid} ok={ok} lots={n_lots}")
        return "done" if ok else "no_lots"
    except Exception as exc:
        msg = str(exc)
        durability = (
            "Hostinger" in msg
            or "push/verify" in msg
            or "missing locally" in msg
            or "SSH" in msg
            or isinstance(exc, FileNotFoundError)
        )
        logger.exception("parse failed %s", item.stable_key)
        mark_parse(
            ledger,
            item.stable_key,
            ok=False,
            error=msg,
            durability_failed=durability,
        )
        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)
        _phase(f"parse_item source={src} id={aid} ok=False error={exc}")
        return "durability" if durability else "error"


def run_parse_assets(
    *,
    repo_root: Path = REPO_ROOT,
    timebox_min: int = PIPELINE_JOB_TIMEBOX_MIN,
    break_stale_lock: bool = True,
    max_parse: int | None = None,
    auction_ids: str | None = None,
    batch_size: int = PARSE_BATCH_SIZE,
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
    t0 = time.monotonic()
    parsed_n = skipped = failed = 0
    capped_run = max_parse is not None and int(max_parse) > 0
    id_filter = _parse_id_set(auction_ids)
    attempted_ids: list[str] = []
    batch_size = max(1, int(batch_size))

    try:
        if media_push_required() and _hostinger_ssh_config() is None:
            raise RuntimeError(
                "parse requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1"
            )

        pulled = pull_ledger(local_path=ledger_path)
        pull_parsed_tree(local_root=parsed_root)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError(
                "ledger pull failed and local ledger is empty — refusing parse"
            )
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
        _phase(f"queue={len(queue)} max_parse={max_parse} batch_size={batch_size}")

        offset = 0
        batch_num = 0
        while offset < len(queue):
            elapsed_min = (time.monotonic() - t0) / 60.0
            if elapsed_min >= timebox_min:
                _phase("timebox reached")
                break

            batch = queue[offset : offset + batch_size]
            offset += len(batch)
            batch_num += 1
            durability_failed_keys: list[str] = []
            _phase(f"batch {batch_num}: selected={len(batch)}")

            for item in batch:
                elapsed_min = (time.monotonic() - t0) / 60.0
                if elapsed_min >= timebox_min:
                    _phase("timebox reached mid-batch")
                    break
                # Refresh item from ledger (retries / prior writes).
                live = ledger.by_key().get(item.stable_key) or item
                if live.parse == "done":
                    skipped += 1
                    continue
                attempted_ids.append(str(live.source_auction_id))
                outcome = _process_one(
                    item=live,
                    ledger=ledger,
                    ledger_path=ledger_path,
                    public_dir=public_dir,
                    pdf_dir=pdf_dir,
                    raw_dir=raw_dir,
                    parsed_root=parsed_root,
                )
                if outcome == "done":
                    parsed_n += 1
                elif outcome == "skipped":
                    skipped += 1
                elif outcome == "durability":
                    failed += 1
                    durability_failed_keys.append(live.stable_key)
                else:
                    failed += 1
                _pause_between_auctions()

            # Batch-end reattempt: save/verify (durability) failures only.
            retry_rounds = max(0, int(PARSE_BATCH_RETRY_ROUNDS))
            for retry_round in range(1, retry_rounds + 1):
                if not durability_failed_keys:
                    break
                elapsed_min = (time.monotonic() - t0) / 60.0
                if elapsed_min >= timebox_min:
                    _phase("timebox during parse batch-end retry; stopping")
                    break
                _phase(
                    f"batch {batch_num} durability retry {retry_round}/{retry_rounds}: "
                    f"failed={len(durability_failed_keys)}"
                )
                still: list[str] = []
                by_key = ledger.by_key()
                for key in durability_failed_keys:
                    live = by_key.get(key)
                    if live is None or live.parse == "done":
                        continue
                    outcome = _process_one(
                        item=live,
                        ledger=ledger,
                        ledger_path=ledger_path,
                        public_dir=public_dir,
                        pdf_dir=pdf_dir,
                        raw_dir=raw_dir,
                        parsed_root=parsed_root,
                    )
                    if outcome in ("done", "skipped"):
                        if outcome == "done":
                            parsed_n += 1
                        else:
                            skipped += 1
                        failed = max(0, failed - 1)
                    elif outcome == "durability":
                        still.append(key)
                    # Content failure on retry — drop from durability set.
                    _pause_between_auctions()
                durability_failed_keys = still

        backlog = len(select_for_parse(load_ledger(ledger_path), limit=None))
        attempted = parsed_n + failed
        budget_ok = fail_budget_ok(
            failed=failed,
            attempted=attempted,
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
        }
        if attempted_ids:
            _phase(f"attempted_ids={','.join(attempted_ids)}")
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
    parser = argparse.ArgumentParser(description="Parse assets lane (one-by-one durable)")
    parser.add_argument("--timebox-min", type=int, default=PIPELINE_JOB_TIMEBOX_MIN)
    parser.add_argument("--max-parse", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=PARSE_BATCH_SIZE)
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
        batch_size=args.batch_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
