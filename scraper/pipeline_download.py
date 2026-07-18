"""Process 1: Download drain — ledger-only HTML/PDF batches with Hostinger flush.

Discovery/bootstrap live in ``pipeline_discover`` (Process 0). This job loops
batches of ``batch_size`` (default 25) until the download backlog is clear.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    DEFAULT_THUMBS_DIR,
    PIPELINE_DOWNLOAD_BATCH_SIZE,
    PIPELINE_DOWNLOAD_MAX_BATCHES,
    PIPELINE_PDF_PUSH_EVERY,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.document_cache import process_auction_documents
from scraper.filters import make_run_id
from scraper.main import enrich_auction, resolve_auction_listing
from scraper.media_sync import media_push_required
from scraper.pdf_downloader import validate_pdf_file
from scraper.pdf_flush import CataloguePdfFlushQueue, mark_pdfs_hostinger_synced
from scraper.pipeline_ledger import (
    estimated_download_runs_to_clear,
    load_ledger,
    mark_download,
    pull_ledger,
    push_ledger,
    select_for_download,
    write_ledger,
)
from scraper.pipeline_markers import reset_download_retry_state
from scraper.raw_store import (
    _hostinger_ssh_config,
    has_raw_html,
    pull_public_pdf_files,
    push_public_media,
    push_raw_store,
    raw_html_rel_path,
)
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.schedule_guard import latest_slot_start
from scraper.telegram_reporter import send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_download")

DEFAULT_PDF_PUSH_EVERY = PIPELINE_PDF_PUSH_EVERY


def _pdf_push_every() -> int:
    import os

    raw = (os.environ.get("PDF_PUSH_EVERY") or str(DEFAULT_PDF_PUSH_EVERY)).strip()
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_PDF_PUSH_EVERY
    return max(1, n)


def _phase(msg: str) -> None:
    print(f"[pipeline_download] {msg}", flush=True)
    logger.info(msg)


def _setup_logging(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "download.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )


def _github_run_url() -> str | None:
    import os

    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def _download_one_mstc(
    *,
    item: Any,
    pdf_dir: Path,
    raw_dir: Path,
    docs_dir: Path,
    thumbs_dir: Path,
    skip_pdf: bool,
    skip_docs: bool,
    docs_remaining: int,
    session: requests.Session,
    stats: dict[str, Any],
    ledger: Any,
) -> tuple[bool, int]:
    """Download one MSTC row. Returns (ok, docs_remaining)."""
    base, _ = resolve_auction_listing(item.source_auction_id)
    base.source = "mstc"
    try:
        downloaded = enrich_auction(
            base,
            pdf_dir=pdf_dir,
            skip_pdf=skip_pdf,
            stats=stats,
            mode="download_only",
            raw_dir=raw_dir,
        )
        if not skip_docs and docs_remaining > 0 and downloaded.lots:
            downloaded, docs_remaining = process_auction_documents(
                downloaded,
                docs_dir=docs_dir,
                thumbs_dir=thumbs_dir,
                skip_docs=False,
                max_docs_remaining=docs_remaining,
                session=session,
                stats=stats,
            )
        has_html = has_raw_html("mstc", item.source_auction_id, raw_dir=raw_dir)
        has_pdf = validate_pdf_file(pdf_dir / f"{item.source_auction_id}.pdf")
        if skip_pdf:
            ok = has_html
        else:
            ok = has_html and has_pdf
        err = None
        if not ok:
            parts = list(downloaded.errors or [])
            if not has_html:
                parts.append("missing raw HTML")
            if not skip_pdf and not has_pdf:
                parts.append("missing or invalid catalogue PDF")
            err = "; ".join(parts) if parts else "download incomplete"
        mark_download(
            ledger,
            item.stable_key,
            ok=ok,
            raw_html_path=raw_html_rel_path("mstc", item.source_auction_id) if has_html else None,
            pdf_path=f"pdfs/{item.source_auction_id}.pdf" if has_pdf else None,
            error=err,
        )
        return ok, docs_remaining
    except Exception as exc:
        logger.exception("download failed for %s", item.stable_key)
        mark_download(ledger, item.stable_key, ok=False, error=str(exc))
        return False, docs_remaining


def run_pipeline_download(
    *,
    repo_root: Path = REPO_ROOT,
    batch_size: int = PIPELINE_DOWNLOAD_BATCH_SIZE,
    max_batches: int = PIPELINE_DOWNLOAD_MAX_BATCHES,
    max_docs_per_run: int = 2000,
    skip_docs: bool = False,
    skip_pdf: bool = False,
    break_stale_lock: bool = True,
    pdf_push_every: int | None = None,
    # Legacy alias: max_download maps to a single-batch cap when set without drain.
    max_download: int | None = None,
) -> dict[str, Any]:
    flush_every = max(1, int(pdf_push_every if pdf_push_every is not None else _pdf_push_every()))
    batch_size = max(1, int(batch_size if max_download is None else min(batch_size, max_download)))
    max_batches = max(1, int(max_batches))

    run_id = f"download_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)

    lock_path = repo_root / "work" / "download.lock"
    acquire_refresh_lock(
        lock_path=lock_path,
        run_id=run_id,
        stale_minutes=360,
        break_stale_lock=break_stale_lock,
    )

    public_dir = repo_root / "web" / "public"
    pdf_dir = Path(DEFAULT_PDF_DIR)
    docs_dir = Path(DEFAULT_DOCS_DIR)
    thumbs_dir = Path(DEFAULT_THUMBS_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "download",
        "started_at": started,
        "batch_size": batch_size,
        "max_batches": max_batches,
        "pdf_push_every": flush_every,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="download_started")

    warnings: list[str] = []
    errors: list[str] = []
    flush_queue: CataloguePdfFlushQueue | None = None
    try:
        if not skip_pdf and media_push_required() and _hostinger_ssh_config() is None:
            raise RuntimeError(
                "download requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1"
            )

        pdf_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        pull_ledger(local_path=ledger_path)
        ledger = load_ledger(ledger_path)

        stats: dict[str, Any] = {
            "html_downloaded": 0,
            "html_failures": 0,
            "pdf_downloaded": 0,
            "pdf_cache_hits": 0,
            "pdf_failures": 0,
            "pdf_failed_ids": [],
            "pdf_hostinger_flushed": 0,
            "pdf_hostinger_flush_batches": 0,
            "pdf_hostinger_flush_failures": 0,
            "documents": {},
            "batches_completed": 0,
        }
        docs_remaining = max_docs_per_run
        session = requests.Session()
        ok_count = 0
        fail_count = 0
        loop_started = time.monotonic()
        batch_reports: list[dict[str, Any]] = []

        flush_queue = CataloguePdfFlushQueue(
            public_dir=public_dir,
            ledger=ledger,
            flush_every=flush_every,
            skip=skip_pdf,
            phase=_phase,
            stats=stats,
            warnings=warnings,
        )

        for batch_num in range(1, max_batches + 1):
            selected = select_for_download(ledger, limit=batch_size, pdf_dir=pdf_dir)
            if not selected:
                _phase(f"download backlog clear after {batch_num - 1} batch(es)")
                break

            # Warm local PDF cache for this batch only.
            if not skip_pdf:
                pdf_names = [f"{i.source_auction_id}.pdf" for i in selected if i.source == "mstc"]
                pull_result = pull_public_pdf_files(public_dir=public_dir, filenames=pdf_names)
                if pull_result.warnings:
                    warnings.extend(pull_result.warnings[:5])

            batch_ok = 0
            batch_fail = 0
            flushed_before = int(stats.get("pdf_hostinger_flushed") or 0)
            _phase(f"batch {batch_num}/{max_batches}: selected={len(selected)}")

            for item in selected:
                if item.source != "mstc":
                    # Non-MSTC download is handled as parse-time live enrich; skip here.
                    continue
                ok, docs_remaining = _download_one_mstc(
                    item=item,
                    pdf_dir=pdf_dir,
                    raw_dir=raw_dir,
                    docs_dir=docs_dir,
                    thumbs_dir=thumbs_dir,
                    skip_pdf=skip_pdf,
                    skip_docs=skip_docs,
                    docs_remaining=docs_remaining,
                    session=session,
                    stats=stats,
                    ledger=ledger,
                )
                if ok:
                    ok_count += 1
                    batch_ok += 1
                    if validate_pdf_file(pdf_dir / f"{item.source_auction_id}.pdf"):
                        flush_queue.enqueue(item.source_auction_id)
                        flushed = flush_queue.maybe_flush()
                        if flushed is not None and flushed.ok:
                            write_ledger(ledger, ledger_path)
                else:
                    fail_count += 1
                    batch_fail += 1

            flush_queue.flush(force=True)
            write_ledger(ledger, ledger_path)
            push_ledger(local_path=ledger_path)
            stats["batches_completed"] = batch_num
            flushed_delta = int(stats.get("pdf_hostinger_flushed") or 0) - flushed_before
            left = estimated_download_runs_to_clear(ledger, cap=batch_size, pdf_dir=pdf_dir)
            # left is runs; also expose item count via select length
            left_items = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir))
            batch_payload = {
                **payload,
                "batch_number": batch_num,
                "batch_ok": batch_ok,
                "batch_failed": batch_fail,
                "batch_flushed": flushed_delta,
                "download_ok": ok_count,
                "download_failed": fail_count,
                "backlog_left": left_items,
                "estimated_batches_left": left,
                "stats": dict(stats),
                "ledger": ledger.status_counts(),
                "warnings": list(warnings[-10:]),
            }
            batch_reports.append(
                {
                    "batch": batch_num,
                    "ok": batch_ok,
                    "failed": batch_fail,
                    "flushed": flushed_delta,
                    "backlog_left": left_items,
                }
            )
            send_telegram_report(batch_payload, event="download_batch_done")
            _phase(
                f"batch {batch_num} done ok={batch_ok} failed={batch_fail} "
                f"flushed=+{flushed_delta} backlog_left={left_items}"
            )

            if left_items <= 0:
                break

        push_raw_store(raw_dir=raw_dir)
        _phase("media: final pdfs/docs/thumbs push to Hostinger")
        media_result = push_public_media(public_dir=public_dir)
        payload["media_push"] = media_result.to_dict()
        if media_result.ok:
            synced_names = [
                f"{i.source_auction_id}.pdf"
                for i in ledger.items
                if i.source == "mstc"
                and i.download == "done"
                and i.media_synced is False
                and i.pdf_path
            ]
            if synced_names:
                mark_pdfs_hostinger_synced(ledger, synced_names, synced=True)
            warnings.append("media push ok")
        else:
            warnings.append(f"media push failed: {media_result.message}")
            if not skip_pdf and media_push_required() and ok_count > 0:
                raise RuntimeError(
                    f"download media push failed (PDFs not confirmed on Hostinger): "
                    f"{media_result.message}"
                )

        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)

        finished = datetime.now(IST).isoformat()
        wall_seconds = time.monotonic() - loop_started
        try:
            slot = latest_slot_start(datetime.now(IST)).strftime("%Y-%m-%dT%H:%M%z")
            reset_download_retry_state(slot_id=slot)
        except Exception as exc:
            warnings.append(f"reset download retry state failed: {exc}")

        backlog_left = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir))
        payload.update(
            {
                "status": "success",
                "finished_at": finished,
                "download_ok": ok_count,
                "download_failed": fail_count,
                "batches_completed": int(stats.get("batches_completed") or 0),
                "batch_reports": batch_reports,
                "backlog_left": backlog_left,
                "stats": stats,
                "ledger": ledger.status_counts(),
                "warnings": warnings,
                "docs_budget_left": docs_remaining,
                "estimated_runs_to_clear": estimated_download_runs_to_clear(
                    ledger, cap=batch_size, pdf_dir=pdf_dir
                ),
                "wall_seconds": round(wall_seconds, 1),
                "ok_per_min": round(ok_count / (wall_seconds / 60.0), 2) if wall_seconds > 0 else None,
            }
        )
        (run_dir / "download_report.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        send_telegram_report(payload, event="download_done")
        return payload
    except Exception as exc:
        logger.exception("pipeline download failed")
        if flush_queue is not None:
            flush_queue.emergency_flush()
        errors.append(str(exc))
        payload["status"] = "failed"
        payload["errors"] = errors
        payload["warnings"] = warnings
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="download_failed")
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline process 1: download drain (ledger-only)")
    parser.add_argument("--batch-size", type=int, default=PIPELINE_DOWNLOAD_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=PIPELINE_DOWNLOAD_MAX_BATCHES)
    parser.add_argument(
        "--max-download",
        type=int,
        default=None,
        help="Optional legacy single-batch cap (limits batch-size for one cycle)",
    )
    parser.add_argument("--max-docs-per-run", type=int, default=2000)
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument(
        "--pdf-push-every",
        type=int,
        default=None,
        help=f"Flush PDFs to Hostinger every N successes (default {PIPELINE_PDF_PUSH_EVERY})",
    )
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_pipeline_download(
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        max_download=args.max_download,
        max_docs_per_run=args.max_docs_per_run,
        skip_docs=args.skip_docs,
        skip_pdf=args.skip_pdf,
        break_stale_lock=args.break_stale_lock,
        pdf_push_every=args.pdf_push_every,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
