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
    DEFAULT_DOCS_DIR,
    DEFAULT_PARSED_DIR,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    DEFAULT_THUMBS_DIR,
    GEM_REQUEUE_MAX_PER_RUN,
    PARSE_ASSETS_MAX_DOCS,
    PARSE_FAIL_BUDGET_ABS,
    PARSE_FAIL_BUDGET_PCT,
    PARSE_WAVE_SIZE,
    PARSE_WORKERS,
    PARSER_CACHE_VERSION,
    PIPELINE_JOB_TIMEBOX_MIN,
    REPO_ROOT,
)
from scraper.filters import make_run_id
from scraper.lane_resume import dispatch_workflow, kick_if_needed, record_resume, should_self_resume
from scraper.media_sync import media_push_required
from scraper.models import AuctionRecord
from scraper.object_store import download_object_to_path, media_r2_only
from scraper.parse_cache import (
    build_parse_artifact,
    file_sha256,
    is_fresh_parse,
    load_parse_artifact,
    local_parsed_path,
    pull_parsed_tree,
    write_parse_artifact,
)
from scraper.parse_engine import worker_parse_mstc
from scraper.parse_flush import flush_parsed_files
from scraper.parse_journal import ParseJournal
from scraper.pipeline_ledger import (
    count_publishable_future,
    fail_budget_ok,
    item_passes_min_closing,
    load_ledger,
    mark_parse,
    media_doc_path,
    media_doc_url,
    pull_ledger,
    push_ledger,
    select_for_parse,
    select_publishable_future,
    write_ledger,
)
from scraper.pipeline_status import publish_pipeline_status, truth_for_telegram
from scraper.raw_store import (
    _hostinger_ssh_config,
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
    """Ensure catalogue PDFs/docs are local — prefer CDN/R2 over Hostinger pull."""
    mstc = [i for i in wave if i.source == "mstc"]
    gem = [i for i in wave if i.source == "gem_forward"]
    if mstc:
        pairs = [(i.source, str(i.source_auction_id)) for i in mstc]
        try:
            pull_raw_files(pairs, raw_dir=raw_dir, timeout_sec=300)
        except Exception as exc:
            logger.warning("raw pull soft-fail: %s", exc)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        for i in mstc:
            host_rel = media_doc_path(i) or f"pdfs/{i.source_auction_id}.pdf"
            local = public_dir / host_rel
            if not local.is_file():
                local = pdf_dir / f"{i.source_auction_id}.pdf"
            if local.is_file() and i.doc_sha256:
                try:
                    if file_sha256(local) == i.doc_sha256:
                        continue
                except Exception:
                    pass
            if local.is_file() and local.stat().st_size > 1000 and not i.doc_sha256:
                continue
            dest = public_dir / host_rel
            download_object_to_path(
                key=host_rel,
                url=media_doc_url(i) or None,
                dest=dest,
            )
    if gem:
        for i in gem:
            rel = media_doc_path(i)
            if not rel:
                continue
            dest = public_dir / rel
            if dest.is_file() and dest.stat().st_size > 0:
                continue
            download_object_to_path(
                key=rel,
                url=media_doc_url(i) or None,
                dest=dest,
            )


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
        "hostinger_doc_path": item.hostinger_doc_path or host_rel,
        "hostinger_doc_url": media_doc_url(item) or item.hostinger_doc_url,
        "object_doc_url": getattr(item, "object_doc_url", None) or media_doc_url(item),
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


def _ensure_gem_catalogue(
    *,
    public_dir: Path,
    source_auction_id: str,
    hostinger_doc_path: str | None,
    hostinger_doc_url: str | None = None,
) -> Path | None:
    from scraper.gem_catalogue_text import resolve_gem_catalogue_path

    path = resolve_gem_catalogue_path(
        public_dir=public_dir,
        source_auction_id=source_auction_id,
        hostinger_doc_path=hostinger_doc_path,
    )
    if path is not None:
        return path
    aid = str(source_auction_id).strip()
    candidates: list[tuple[str, Path]] = []
    if hostinger_doc_path:
        rel = hostinger_doc_path.lstrip("/")
        candidates.append((rel, public_dir / rel))
    for folder in ("docs/gem", "pdfs/gem"):
        for ext in (".pdf", ".docx"):
            rel = f"{folder}/{aid}{ext}"
            candidates.append((rel, public_dir / rel))
    for key, dest in candidates:
        try:
            result = download_object_to_path(
                key=key,
                url=hostinger_doc_url if key == (hostinger_doc_path or "").lstrip("/") else None,
                dest=dest,
            )
            if result.get("ok") and dest.is_file() and dest.stat().st_size > 200:
                return dest
        except Exception as exc:
            logger.debug("GeM catalogue pull %s failed: %s", key, exc)
    return resolve_gem_catalogue_path(
        public_dir=public_dir,
        source_auction_id=source_auction_id,
        hostinger_doc_path=hostinger_doc_path,
    )


def _hydrate_mstc_docs(
    record_dict: dict[str, Any],
    *,
    docs_dir: Path,
    thumbs_dir: Path,
    docs_remaining: int,
    session: Any,
    stats: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    if docs_remaining <= 0:
        return record_dict, docs_remaining
    try:
        record = AuctionRecord.model_validate(record_dict)
    except Exception as exc:
        logger.warning("MSTC doc hydrate validate failed: %s", exc)
        return record_dict, docs_remaining
    # Prefer lots that name a photo but have no ready preview.
    needs = False
    for lot in record.lots or []:
        if lot.photo_file and not (lot.preview_images or []):
            needs = True
            break
        for doc in lot.documents or []:
            if getattr(doc, "status", None) in {"pending", "pending_cache", "failed", "skipped"}:
                needs = True
                break
        if needs:
            break
    if not needs and not any(lot.photo_file or lot.annexure_file for lot in (record.lots or [])):
        return record_dict, docs_remaining
    from scraper.document_cache import process_auction_documents

    refreshed, remaining = process_auction_documents(
        record,
        docs_dir=docs_dir,
        thumbs_dir=thumbs_dir,
        skip_docs=False,
        max_docs_remaining=docs_remaining,
        session=session,
        stats=stats,
    )
    return refreshed.model_dump(mode="json"), remaining

def _requeue_stale_gem_parses(
    ledger: Any,
    *,
    target_version: str | None = None,
    max_requeue: int | None = None,
) -> tuple[list[Any], int]:
    """Requeue GeM parse=done rows whose ledger parser_version lags target.

    Ledger is source of truth (CI runners have empty work/parsed/). Returns
    (items_to_append, skipped_already_current). Never uses missing local files
    as a staleness signal.
    """
    target = str(target_version or PARSER_CACHE_VERSION)
    cap = int(GEM_REQUEUE_MAX_PER_RUN if max_requeue is None else max_requeue)
    if cap < 0:
        cap = 0
    candidates: list[Any] = []
    skipped_current = 0
    for item in ledger.items:
        if item.source != "gem_forward":
            continue
        if item.parse != "done" or item.download != "done" or item.removed_from_source:
            continue
        if not media_doc_url(item) or not media_doc_path(item):
            continue
        if str(item.parser_version or "") == target:
            skipped_current += 1
            continue
        candidates.append(item)

    # Prefer future-closing auctions when capping.
    future: list[Any] = []
    other: list[Any] = []
    for item in candidates:
        try:
            if item_passes_min_closing(item):
                future.append(item)
            else:
                other.append(item)
        except Exception:
            other.append(item)
    ordered = future + other
    selected = ordered[:cap] if cap else []
    for item in selected:
        item.parse = "pending"
        item.parse_error = None
    return selected, skipped_current


def merge_parse_queue_with_gem_upgrades(
    pending: list[Any],
    gem_upgrades: list[Any],
) -> list[Any]:
    """MSTC/GeM true pending first; append GeM version upgrades (no front-load)."""
    seen = {i.stable_key for i in pending}
    tail = [i for i in gem_upgrades if i.stable_key not in seen]
    return list(pending) + tail


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
    timing = {"prefetch_s": 0.0, "cpu_s": 0.0, "flush_s": 0.0, "docs_s": 0.0}
    docs_remaining = max(0, int(PARSE_ASSETS_MAX_DOCS))
    docs_stats: dict[str, Any] = {
        "documents": {
            "refs_found": 0,
            "attempted": 0,
            "downloaded": 0,
            "cache_hits": 0,
            "thumbnails_ready": 0,
            "failed": 0,
            "skipped_due_limit": 0,
            "failed_by_reason": {},
            "failed_by_doc_type": {},
        }
    }
    media_dirty = False
    gem_catalogue_n = 0
    docs_session = None
    if docs_remaining > 0:
        import requests

        docs_session = requests.Session()

    try:
        if media_push_required() and not media_r2_only() and _hostinger_ssh_config() is None:
            raise RuntimeError(
                "parse requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1 "
                "and MEDIA_R2_ONLY is off"
            )

        pulled = pull_ledger(local_path=ledger_path)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError("ledger pull failed and local ledger is empty — refusing parse")

        pulled_parsed_n = pull_parsed_tree(local_root=parsed_root)
        if pulled_parsed_n:
            _phase(f"pulled_parsed_artifacts={pulled_parsed_n}")

        queue = select_for_parse(ledger, limit=None)
        stale_gem, skipped_gem_current = _requeue_stale_gem_parses(ledger)
        if stale_gem or skipped_gem_current:
            queue = merge_parse_queue_with_gem_upgrades(queue, stale_gem)
            _phase(
                f"stale_gem_requeue={len(stale_gem)} skipped_current_version={skipped_gem_current} "
                f"parser_version={PARSER_CACHE_VERSION} cap={GEM_REQUEUE_MAX_PER_RUN}"
            )
        if id_filter is not None:
            queue = [i for i in queue if str(i.source_auction_id) in id_filter]
            if not queue:
                queue = [
                    i
                    for i in ledger.items
                    if str(i.source_auction_id) in id_filter
                    and i.download == "done"
                    and media_doc_url(i)
                    and media_doc_path(i)
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
                if not media_doc_url(item) or not media_doc_path(item):
                    mark_parse(
                        ledger,
                        item.stable_key,
                        ok=False,
                        error="missing CDN media URL — download required",
                        durability_failed=True,
                    )
                    failed += 1
                    continue
                out_path = local_parsed_path(item.source, item.source_auction_id, root=parsed_root)
                host_rel = media_doc_path(item)
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
                    # P2: catalogue PDF/DOCX → body + optional page-1 thumb
                    try:
                        from scraper.gem_catalogue_text import merge_gem_catalogue_into_record

                        cat = _ensure_gem_catalogue(
                            public_dir=public_dir,
                            source_auction_id=aid,
                            hostinger_doc_path=item.hostinger_doc_path,
                            hostinger_doc_url=item.hostinger_doc_url,
                        )
                        if cat is not None:
                            before = (rec.get("item_summary") or "")[:80]
                            rec = merge_gem_catalogue_into_record(rec, pdf_path=cat)
                            gem_catalogue_n += 1
                            if (rec.get("item_summary") or "")[:80] != before:
                                media_dirty = True
                            lots0 = rec.get("lots") or []
                            if (
                                isinstance(lots0, list)
                                and lots0
                                and isinstance(lots0[0], dict)
                                and (lots0[0].get("preview_images") or [])
                            ):
                                media_dirty = True
                    except Exception as exc:
                        logger.warning("GeM catalogue extract failed %s: %s", aid, exc)
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
                            record_dict = dict(result["record"])
                            if docs_remaining > 0 and docs_session is not None:
                                td = time.perf_counter()
                                before_dl = int(
                                    docs_stats["documents"].get("downloaded") or 0
                                )
                                before_th = int(
                                    docs_stats["documents"].get("thumbnails_ready") or 0
                                )
                                record_dict, docs_remaining = _hydrate_mstc_docs(
                                    record_dict,
                                    docs_dir=DEFAULT_DOCS_DIR,
                                    thumbs_dir=DEFAULT_THUMBS_DIR,
                                    docs_remaining=docs_remaining,
                                    session=docs_session,
                                    stats=docs_stats,
                                )
                                timing["docs_s"] += time.perf_counter() - td
                                after_dl = int(
                                    docs_stats["documents"].get("downloaded") or 0
                                )
                                after_th = int(
                                    docs_stats["documents"].get("thumbnails_ready") or 0
                                )
                                if after_dl > before_dl or after_th > before_th:
                                    media_dirty = True
                            out_path = local_parsed_path("mstc", aid, root=parsed_root)
                            artifact = build_parse_artifact(
                                record=record_dict,
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

        if media_dirty:
            try:
                from scraper.raw_store import push_public_media

                media_result = push_public_media(public_dir=public_dir)
                _phase(f"media_push docs/thumbs: {media_result.to_dict()}")
            except Exception as exc:
                logger.warning("media push after parse-assets failed: %s", exc)
                _phase(f"media_push failed: {exc}")

        if docs_remaining <= 0 and int(PARSE_ASSETS_MAX_DOCS) > 0:
            kicked_media, media_reason = kick_if_needed(
                "pipeline-media-backfill.yml",
                reason="parse_assets_doc_budget_exhausted",
                backlog=1,
                inputs={"max_docs": "500", "auction_ids": ""},
            )
            if kicked_media:
                _phase(f"media_backfill kick: {media_reason}")
                record_resume("media_backfill_kick", {"reason": media_reason})

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

        # Event chain: wake deploy when new future-closing publishable rows exist
        ledger_final = load_ledger(ledger_path)
        future_n = count_publishable_future(ledger_final)
        future_pending_deploy = sum(
            1 for i in select_publishable_future(ledger_final) if i.deploy != "done"
        )
        kicked_deploy = False
        deploy_kick_reason = ""
        if (parsed_n > 0 or skipped > 0) and future_pending_deploy > 0:
            kicked_deploy, deploy_kick_reason = kick_if_needed(
                "pipeline-build-deploy.yml",
                reason="parse_done_future_publishable",
                backlog=future_pending_deploy,
                inputs={"allow_small_export": "true"},
            )
            if kicked_deploy:
                record_resume(
                    "deploy_kick",
                    {
                        "reason": deploy_kick_reason,
                        "future_pending_deploy": future_pending_deploy,
                    },
                )

        truth = publish_pipeline_status(
            ledger_final,
            lane="parse",
            wake_reason=deploy_kick_reason or reason or "complete",
            extra={
                "parsed": parsed_n,
                "deploy_kick": kicked_deploy,
                "future_pending_deploy": future_pending_deploy,
            },
        )

        elapsed = time.monotonic() - t0
        status = "Complete" if backlog == 0 else "Paused · timebox"
        send_lane_report(
            "parse",
            "finished",
            {
                "parsed": parsed_n,
                "skipped_fresh": skipped,
                "failed": failed,
                "ready_to_process": backlog,
                "ready_for_site": future_n,
                "live_on_site": truth.get("live_export_count"),
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
            "publishable_future": future_n,
            "deploy_kick": kicked_deploy,
            "gem_catalogue_extracted": gem_catalogue_n,
            "docs_remaining": docs_remaining,
            "docs_stats": docs_stats.get("documents"),
            "truth": truth_for_telegram(truth),
        }
        if attempted_ids:
            _phase(f"attempted_ids={','.join(attempted_ids[:50])}{'…' if len(attempted_ids)>50 else ''}")
        _phase(
            f"done parsed={parsed_n} skipped={skipped} failed={failed} "
            f"elapsed={elapsed:.1f}s rate={payload['items_per_sec']}/s "
            f"future={future_n} kick_deploy={kicked_deploy} timing={timing}"
        )
        (run_dir / "parse_assets_report.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return payload
    except Exception as exc:
        send_lane_report("parse", "failed", {"error": str(exc)})
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
