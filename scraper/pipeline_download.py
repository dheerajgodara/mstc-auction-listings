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
    DOWNLOAD_BATCH_RETRY_ROUNDS,
    DOWNLOAD_FAIL_BUDGET_ABS,
    DOWNLOAD_FAIL_BUDGET_PCT,
    DOWNLOAD_SUCCESS_PAUSE_SEC,
    PIPELINE_DOWNLOAD_BATCH_SIZE,
    PIPELINE_DOWNLOAD_CAP_CATCHUP,
    PIPELINE_DOWNLOAD_MAX_BATCHES,
    PIPELINE_JOB_TIMEBOX_MIN,
    PIPELINE_PDF_PUSH_EVERY,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.document_cache import process_auction_documents
from scraper.filters import make_run_id
from scraper.main import enrich_auction, resolve_auction_listing
from scraper.media_sync import media_push_required
from scraper.pdf_downloader import validate_pdf_file
from scraper.pdf_flush import (
    CataloguePdfFlushQueue,
    _sha256_file,
    verify_hostinger_doc_url,
)
from scraper.pipeline_ledger import (
    estimated_download_runs_to_clear,
    fail_budget_ok,
    load_ledger,
    mark_download,
    public_doc_url,
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
    push_public_pdf_files,
    push_raw_store,
    raw_html_rel_path,
    save_raw_html,
)
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.schedule_guard import latest_slot_start
from scraper.telegram_reporter import send_lane_report, send_telegram_report
from scraper.lane_resume import dispatch_workflow, record_resume, should_self_resume

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
    public_dir: Path,
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
    """Fetch → save Hostinger → HTTP 200 check (one try each). Fail → pending."""
    import shutil

    aid = str(item.source_auction_id)
    docs_left = docs_remaining

    try:
        base, _ = resolve_auction_listing(aid)
        base.source = "mstc"
        downloaded = enrich_auction(
            base,
            pdf_dir=pdf_dir,
            skip_pdf=skip_pdf,
            stats=stats,
            mode="download_only",
            raw_dir=raw_dir,
        )
        if not skip_docs and docs_left > 0 and downloaded.lots:
            downloaded, docs_left = process_auction_documents(
                downloaded,
                docs_dir=docs_dir,
                thumbs_dir=thumbs_dir,
                skip_docs=False,
                max_docs_remaining=docs_left,
                session=session,
                stats=stats,
            )
        has_html = has_raw_html("mstc", aid, raw_dir=raw_dir)
        has_pdf = skip_pdf or validate_pdf_file(pdf_dir / f"{aid}.pdf")
        if not (has_html and has_pdf):
            parts = list(downloaded.errors or [])
            if not has_html:
                parts.append("missing raw HTML")
            if not skip_pdf and not has_pdf:
                parts.append("missing or invalid catalogue PDF")
            raise RuntimeError("; ".join(parts) if parts else "download incomplete")
    except Exception as exc:
        logger.exception("download fetch failed for %s", item.stable_key)
        mark_download(ledger, item.stable_key, ok=False, error=str(exc))
        return False, docs_left

    item.raw_html_path = raw_html_rel_path("mstc", aid)
    if skip_pdf:
        mark_download(
            ledger,
            item.stable_key,
            ok=False,
            error="skip_pdf set — Hostinger durability required for download=done",
            raw_html_path=item.raw_html_path,
        )
        return False, docs_left

    rel = f"pdfs/{aid}.pdf"
    local_pdf = pdf_dir / f"{aid}.pdf"
    public_pdf = public_dir / "pdfs" / f"{aid}.pdf"

    try:
        public_pdf.parent.mkdir(parents=True, exist_ok=True)
        if local_pdf.resolve() != public_pdf.resolve():
            shutil.copy2(local_pdf, public_pdf)
        result = push_public_pdf_files(public_dir=public_dir, filenames=[f"{aid}.pdf"])
        if not result.ok:
            raise RuntimeError(result.message or "Hostinger PDF push failed")
        pushed = set(result.files or [])
        if f"{aid}.pdf" not in pushed and media_push_required():
            raise RuntimeError(f"Hostinger PDF push did not confirm {aid}.pdf")
    except Exception as exc:
        mark_download(ledger, item.stable_key, ok=False, error=str(exc), raw_html_path=item.raw_html_path)
        return False, docs_left

    url = public_doc_url(rel)
    try:
        if not verify_hostinger_doc_url(url):
            raise RuntimeError(f"Hostinger URL not HTTP 200: {url}")
    except Exception as exc:
        mark_download(ledger, item.stable_key, ok=False, error=str(exc), raw_html_path=item.raw_html_path)
        return False, docs_left

    mark_download(
        ledger,
        item.stable_key,
        ok=True,
        hostinger_doc_path=rel,
        hostinger_doc_url=url,
        doc_sha256=_sha256_file(local_pdf),
        raw_html_path=item.raw_html_path,
        content_changed=True,
    )
    stats["pdf_hostinger_flushed"] = int(stats.get("pdf_hostinger_flushed") or 0) + 1
    return True, docs_left


def _download_one_gem(
    *,
    item: Any,
    raw_dir: Path,
    ledger: Any,
    public_dir: Path,
) -> bool:
    """Fetch → save Hostinger → HTTP 200 check (one try each). Fail → pending."""
    import hashlib

    from scraper.gem_forward_client import GemForwardClient
    from scraper.gem_scrap_samples_fetch import _download_binary

    aid = str(item.source_auction_id or "").strip()
    portal = (getattr(item, "portal_doc_url", None) or "").strip()
    if not portal:
        mark_download(ledger, item.stable_key, ok=False, error="missing portal_doc_url")
        return False

    try:
        client = GemForwardClient()
        client.init_session()
        detail = getattr(item, "detail_url", None) or ""
        if "/eprocure/" in str(detail):
            notice_path = "/eprocure/" + str(detail).split("/eprocure/", 1)[-1]
            try:
                html = client.get_html(notice_path)
                save_raw_html("gem_forward", aid, html, raw_dir=raw_dir)
            except Exception:
                pass
        body = _download_binary(client, portal)
        if len(body) < 500:
            raise RuntimeError(f"gem doc too small ({len(body)} bytes)")
    except Exception as exc:
        logger.exception("gem download failed for %s", item.stable_key)
        mark_download(ledger, item.stable_key, ok=False, error=str(exc))
        return False

    ext = "pdf" if body[:4] == b"%PDF" else "bin"
    rel = f"docs/gem/{aid}.{ext}"
    rel_dir = public_dir / "docs" / "gem"
    out_path = rel_dir / f"{aid}.{ext}"

    try:
        rel_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(body)
        push = push_public_media(public_dir=public_dir, timeout_sec=300)
        if not push.ok and media_push_required():
            raise RuntimeError(f"Hostinger docs push failed: {push.message}")
    except Exception as exc:
        mark_download(ledger, item.stable_key, ok=False, error=str(exc))
        return False

    url = public_doc_url(rel)
    try:
        if not verify_hostinger_doc_url(url):
            raise RuntimeError(f"Hostinger URL not HTTP 200: {url}")
    except Exception as exc:
        mark_download(ledger, item.stable_key, ok=False, error=str(exc))
        return False

    mark_download(
        ledger,
        item.stable_key,
        ok=True,
        hostinger_doc_path=rel,
        hostinger_doc_url=url,
        doc_sha256=hashlib.sha256(body).hexdigest(),
        raw_html_path=raw_html_rel_path("gem_forward", aid)
        if has_raw_html("gem_forward", aid, raw_dir=raw_dir)
        else None,
        content_changed=True,
    )
    return True


def _pause_between_auctions() -> None:
    """Always wait between auctions (success or fail)."""
    time.sleep(max(0.0, DOWNLOAD_SUCCESS_PAUSE_SEC))


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
    # Per-run unique-auction cap (default 2000). Skips self-resume when set.
    max_download: int | None = PIPELINE_DOWNLOAD_CAP_CATCHUP,
    source: str = "mstc",
) -> dict[str, Any]:
    source = (source or "mstc").strip().lower()
    lane_id = "download_mstc" if source == "mstc" else "download_gem"
    flush_every = max(1, int(pdf_push_every if pdf_push_every is not None else _pdf_push_every()))
    batch_size = max(1, int(batch_size))
    # Hard ceiling: never process more than catch-up cap unique auctions per run.
    if max_download is None or int(max_download) <= 0:
        run_item_cap = int(PIPELINE_DOWNLOAD_CAP_CATCHUP)
        capped_run = True
    else:
        run_item_cap = int(max_download)
        capped_run = True
    batch_size = min(batch_size, run_item_cap)
    # Enough batches to reach the cap (do not collapse capped runs to max_batches=1).
    needed = max(1, (run_item_cap + batch_size - 1) // batch_size)
    max_batches = max(1, max(int(max_batches), needed))

    run_id = f"download_{source}_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)

    lock_path = repo_root / "work" / f"download_{source}.lock"
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
    loop_t0 = time.monotonic()

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "download",
        "source": source,
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
    skipped_existing = 0
    try:
        if source == "mstc" and not skip_pdf and media_push_required() and _hostinger_ssh_config() is None:
            raise RuntimeError(
                "download requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1"
            )

        pdf_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        pulled = pull_ledger(local_path=ledger_path)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError(
                "ledger pull failed and local ledger is empty — refusing to continue "
                "(would risk wiping Hostinger ledger on push)"
            )
        eligible_n = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir, source=source))
        _phase(
            f"ledger items={len(ledger.items)} counts={ledger.status_counts()} "
            f"download_eligible[{source}]={eligible_n}"
        )

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
        attempted_ids: list[str] = []
        attempted_keys: set[str] = set()
        batch_reports: list[dict[str, Any]] = []

        # Per-item durable path (fetch→push→HTTP 200); flush queue unused.
        flush_queue = CataloguePdfFlushQueue(
            public_dir=public_dir,
            ledger=ledger,
            flush_every=flush_every,
            skip=True,
            phase=_phase,
            stats=stats,
            warnings=warnings,
        )

        def _unique_attempted() -> int:
            return len(attempted_keys)

        def _download_item(item: Any) -> bool:
            nonlocal docs_remaining
            if source == "mstc":
                if item.source != "mstc":
                    return False
                if item.download == "done":
                    return True
                ok, docs_remaining = _download_one_mstc(
                    item=item,
                    pdf_dir=pdf_dir,
                    public_dir=public_dir,
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
            else:
                if item.source != "gem_forward":
                    return False
                ok = _download_one_gem(
                    item=item, raw_dir=raw_dir, ledger=ledger, public_dir=public_dir
                )
            attempted_ids.append(str(item.source_auction_id))
            attempted_keys.add(item.stable_key)
            _phase(f"download_item source={source} id={item.source_auction_id} ok={ok}")
            write_ledger(ledger, ledger_path)
            _pause_between_auctions()
            return bool(ok)

        for batch_num in range(1, max_batches + 1):
            elapsed_min = (time.monotonic() - loop_t0) / 60.0
            if elapsed_min >= PIPELINE_JOB_TIMEBOX_MIN:
                _phase(f"timebox reached ({elapsed_min:.0f}m); stopping batch loop")
                break
            if _unique_attempted() >= run_item_cap:
                _phase(f"max-download cap reached ({run_item_cap})")
                break

            remaining = run_item_cap - _unique_attempted()
            select_n = min(batch_size, remaining)
            selected = select_for_download(
                ledger, limit=select_n, pdf_dir=pdf_dir, source=source
            )
            if not selected:
                _phase(f"download backlog clear after {batch_num - 1} batch(es)")
                break

            if source == "mstc" and not skip_pdf:
                pdf_names = [f"{i.source_auction_id}.pdf" for i in selected]
                pull_result = pull_public_pdf_files(public_dir=public_dir, filenames=pdf_names)
                if pull_result.warnings:
                    warnings.extend(pull_result.warnings[:5])

            batch_ok = 0
            batch_fail = 0
            failed_keys: list[str] = []
            _phase(f"batch {batch_num}/{max_batches}: selected={len(selected)} source={source}")

            for item in selected:
                if _unique_attempted() >= run_item_cap and item.stable_key not in attempted_keys:
                    break
                if item.download == "done":
                    skipped_existing += 1
                    continue
                ok = _download_item(item)
                if ok:
                    ok_count += 1
                    batch_ok += 1
                else:
                    fail_count += 1
                    batch_fail += 1
                    failed_keys.append(item.stable_key)

            # Batch-end reattempts: only failed IDs from this batch, up to N rounds.
            retry_rounds = max(0, int(DOWNLOAD_BATCH_RETRY_ROUNDS))
            for retry_round in range(1, retry_rounds + 1):
                if not failed_keys:
                    break
                elapsed_min = (time.monotonic() - loop_t0) / 60.0
                if elapsed_min >= PIPELINE_JOB_TIMEBOX_MIN:
                    _phase("timebox during batch-end retry; stopping retries")
                    break
                _phase(
                    f"batch {batch_num} retry round {retry_round}/{retry_rounds}: "
                    f"failed={len(failed_keys)}"
                )
                still_failed: list[str] = []
                by_key = ledger.by_key()
                for key in failed_keys:
                    item = by_key.get(key)
                    if item is None or item.download == "done":
                        continue
                    ok = _download_item(item)
                    if ok:
                        ok_count += 1
                        batch_ok += 1
                        fail_count = max(0, fail_count - 1)
                        batch_fail = max(0, batch_fail - 1)
                    else:
                        still_failed.append(key)
                failed_keys = still_failed

            stats["batches_completed"] = batch_num
            batch_reports.append(
                {
                    "batch": batch_num,
                    "ok": batch_ok,
                    "fail": batch_fail,
                    "retry_left": len(failed_keys),
                }
            )
            push_ledger(local_path=ledger_path)

        backlog_left = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir, source=source))
        attempted = ok_count + fail_count
        budget_ok = fail_budget_ok(
            failed=fail_count,
            attempted=attempted,
            pct=DOWNLOAD_FAIL_BUDGET_PCT,
            absolute=DOWNLOAD_FAIL_BUDGET_ABS,
        )
        elapsed_min = (time.monotonic() - loop_t0) / 60.0
        # Capped runs (default 2000) do not self-resume; cron/autonomy kick the next drain.
        resume = False
        resume_reason = "capped_run"
        if not capped_run:
            resume, resume_reason = should_self_resume(
                backlog_left=backlog_left,
                failed=fail_count,
                attempted=attempted,
                fail_budget_ok=budget_ok,
                elapsed_min=elapsed_min,
                timebox_min=PIPELINE_JOB_TIMEBOX_MIN,
            )
            if resume:
                wf = (
                    "pipeline-download-mstc.yml"
                    if source == "mstc"
                    else "pipeline-download-gem.yml"
                )
                record_resume(lane_id, {"reason": resume_reason, "backlog_left": backlog_left})
                dispatch_workflow(wf)

        finished = datetime.now(IST).isoformat()
        payload.update(
            {
                "status": "success",
                "finished_at": finished,
                "ok_count": ok_count,
                "fail_count": fail_count,
                "download_ok": ok_count,
                "skipped_existing": skipped_existing,
                "attempted_ids": attempted_ids,
                "unique_attempted": len(attempted_keys),
                "max_download": run_item_cap,
                "backlog_left": backlog_left,
                "fail_budget_ok": budget_ok,
                "resume_next": resume,
                "resume_reason": resume_reason,
                "stats": stats,
                "batches_completed": int(stats.get("batches_completed") or 0),
                "batch_reports": batch_reports,
                "ledger": ledger.status_counts(),
                "warnings": warnings,
                "estimated_runs_to_clear": estimated_download_runs_to_clear(
                    ledger, cap=batch_size, pdf_dir=pdf_dir, source=source
                ),
            }
        )
        (run_dir / "download_report.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
        send_telegram_report(payload, event="download_done")
        status = "Complete" if backlog_left == 0 else "Paused · timebox"
        send_lane_report(
            lane_id,
            "finished",
            {
                "status": status if backlog_left else "Complete",
                "downloaded": ok_count,
                "skipped_existing": skipped_existing,
                "failed": fail_count,
                "backlog_left": backlog_left,
                "fail_budget_ok": budget_ok,
                "resume_next": resume,
            },
            noop=attempted == 0 and backlog_left == 0,
        )
        _phase(f"done ok={ok_count} fail={fail_count} backlog={backlog_left}")
        if attempted_ids:
            _phase(f"attempted_ids={','.join(attempted_ids)}")
        return payload
    except Exception as exc:
        logger.exception("pipeline download failed")
        errors.append(str(exc))
        payload["status"] = "failed"
        payload["errors"] = errors
        payload["warnings"] = warnings
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="download_failed")
        send_lane_report(lane_id, "failed", {"error": str(exc), "backlog_left": "?"})
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline download lane (MSTC or GeM)")
    parser.add_argument("--batch-size", type=int, default=PIPELINE_DOWNLOAD_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=PIPELINE_DOWNLOAD_MAX_BATCHES)
    parser.add_argument(
        "--max-download",
        type=int,
        default=PIPELINE_DOWNLOAD_CAP_CATCHUP,
        help="Unique auctions attempted per run (default 2000)",
    )
    parser.add_argument("--max-docs-per-run", type=int, default=2000)
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--pdf-push-every", type=int, default=None)
    parser.add_argument("--source", default="mstc", choices=["mstc", "gem_forward"])
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
        source=args.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
