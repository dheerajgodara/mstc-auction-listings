"""Fast download lane: parallel portal fetch → batch Hostinger flush → HTTP-200 → done."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import (
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    DOWNLOAD_BATCH_RETRY_ROUNDS,
    DOWNLOAD_FAIL_BUDGET_ABS,
    DOWNLOAD_FAIL_BUDGET_PCT,
    DOWNLOAD_SUCCESS_PAUSE_SEC,
    DOWNLOAD_WAVE_SIZE,
    PIPELINE_DOWNLOAD_BATCH_SIZE,
    PIPELINE_DOWNLOAD_CAP_CATCHUP,
    PIPELINE_DOWNLOAD_MAX_BATCHES,
    PIPELINE_JOB_TIMEBOX_MIN,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.download_engine import fetch_gem_to_local, fetch_mstc_to_local, worker_count_for_source
from scraper.download_flush import flush_download_files
from scraper.download_journal import DownloadJournal
from scraper.download_throttle import DownloadThrottle
from scraper.filters import make_run_id
from scraper.lane_resume import dispatch_workflow, kick_if_needed, record_resume, should_self_resume
from scraper.media_sync import media_push_required
from scraper.pipeline_ledger import (
    count_parse_eligible,
    estimated_download_runs_to_clear,
    fail_budget_ok,
    load_ledger,
    mark_download,
    pull_ledger,
    push_ledger,
    select_for_download,
    write_ledger,
)
from scraper.pipeline_status import publish_pipeline_status, truth_for_telegram
from scraper.raw_store import _hostinger_ssh_config, pull_public_pdf_files
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report, send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_download")


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


def _pause_between_auctions() -> None:
    """Legacy hook; default pause is 0 (adaptive throttle owns pacing)."""
    time.sleep(max(0.0, DOWNLOAD_SUCCESS_PAUSE_SEC))


def _apply_fetch_failures(ledger: Any, results: list[dict[str, Any]]) -> None:
    for r in results:
        if r.get("ok"):
            continue
        mark_download(
            ledger,
            str(r["stable_key"]),
            ok=False,
            error=str(r.get("error") or "fetch failed"),
            raw_html_path=r.get("raw_html_path"),
        )


def _commit_verified(
    ledger: Any,
    verified: list[dict[str, Any]],
    *,
    stats: dict[str, Any],
) -> int:
    n = 0
    for r in verified:
        mark_download(
            ledger,
            str(r["stable_key"]),
            ok=True,
            hostinger_doc_path=str(r["hostinger_doc_path"]),
            hostinger_doc_url=str(r["hostinger_doc_url"]),
            doc_sha256=r.get("doc_sha256"),
            raw_html_path=r.get("raw_html_path"),
            content_changed=True,
        )
        n += 1
    stats["pdf_hostinger_flushed"] = int(stats.get("pdf_hostinger_flushed") or 0) + n
    return n


def _mark_unverified_pending(
    ledger: Any,
    pending_ok: list[dict[str, Any]],
    verified_keys: set[str],
    *,
    error: str,
) -> None:
    for r in pending_ok:
        key = str(r["stable_key"])
        if key in verified_keys:
            continue
        mark_download(
            ledger,
            key,
            ok=False,
            error=error,
            raw_html_path=r.get("raw_html_path"),
        )


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
    max_download: int | None = PIPELINE_DOWNLOAD_CAP_CATCHUP,
    source: str = "mstc",
    wave_size: int | None = None,
) -> dict[str, Any]:
    del max_docs_per_run, skip_docs, pdf_push_every  # reserved / unused in fast path
    source = (source or "mstc").strip().lower()
    lane_id = "download_mstc" if source == "mstc" else "download_gem"
    wave_size = max(1, int(wave_size if wave_size is not None else DOWNLOAD_WAVE_SIZE))
    batch_size = max(1, int(batch_size))
    wave_size = max(wave_size, batch_size) if batch_size else wave_size

    if max_download is None or int(max_download) <= 0:
        run_item_cap = int(PIPELINE_DOWNLOAD_CAP_CATCHUP)
        capped_run = True
    else:
        run_item_cap = int(max_download)
        capped_run = True
    batch_size = min(batch_size, run_item_cap)
    wave_size = min(wave_size, run_item_cap)
    needed = max(1, (run_item_cap + wave_size - 1) // wave_size)
    max_batches = max(1, max(int(max_batches), needed))
    workers = worker_count_for_source(source)

    run_id = f"download_{source}_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)
    journal = DownloadJournal(run_dir / "download_journal.jsonl")

    lock_path = repo_root / "work" / f"download_{source}.lock"
    acquire_refresh_lock(
        lock_path=lock_path,
        run_id=run_id,
        stale_minutes=360,
        break_stale_lock=break_stale_lock,
    )

    public_dir = repo_root / "web" / "public"
    pdf_dir = Path(DEFAULT_PDF_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    loop_t0 = time.monotonic()
    throttle = DownloadThrottle()

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "download",
        "source": source,
        "started_at": started,
        "batch_size": batch_size,
        "wave_size": wave_size,
        "fetch_workers": workers,
        "max_batches": max_batches,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="download_started")

    warnings: list[str] = []
    errors: list[str] = []
    skipped_existing = 0
    timing = {"fetch_s": 0.0, "flush_s": 0.0}
    try:
        if media_push_required() and _hostinger_ssh_config() is None:
            raise RuntimeError(
                "download requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1"
            )

        pdf_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        (public_dir / "pdfs").mkdir(parents=True, exist_ok=True)
        (public_dir / "docs" / "gem").mkdir(parents=True, exist_ok=True)

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
            f"download_eligible[{source}]={eligible_n} wave={wave_size} workers={workers}"
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
            "waves_completed": 0,
        }
        ok_count = 0
        fail_count = 0
        attempted_ids: list[str] = []
        attempted_keys: set[str] = set()
        batch_reports: list[dict[str, Any]] = []

        gem_client = None
        if source == "gem_forward":
            from scraper.gem_forward_client import GemForwardClient

            gem_client = GemForwardClient()
            gem_client.init_session()

        def _unique_attempted() -> int:
            return len(attempted_keys)

        def _fetch_one(item: Any) -> dict[str, Any]:
            if source == "mstc":
                return fetch_mstc_to_local(
                    item=item,
                    pdf_dir=pdf_dir,
                    public_dir=public_dir,
                    raw_dir=raw_dir,
                    skip_pdf=skip_pdf,
                    stats=stats,
                    throttle=throttle,
                )
            return fetch_gem_to_local(
                item=item,
                raw_dir=raw_dir,
                public_dir=public_dir,
                client=gem_client,
                throttle=throttle,
            )

        def _process_wave(selected: list[Any], *, wave_num: int) -> tuple[int, int, list[str]]:
            nonlocal ok_count, fail_count
            batch_ok = 0
            batch_fail = 0
            failed_keys: list[str] = []

            if source == "mstc" and not skip_pdf:
                pdf_names = [f"{i.source_auction_id}.pdf" for i in selected]
                pull_result = pull_public_pdf_files(public_dir=public_dir, filenames=pdf_names)
                if pull_result.warnings:
                    warnings.extend(pull_result.warnings[:5])

            # Parallel portal fetch
            t_fetch = time.monotonic()
            results: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=min(workers, len(selected))) as pool:
                futs = {pool.submit(_fetch_one, item): item for item in selected}
                for fut in as_completed(futs):
                    item = futs[fut]
                    try:
                        r = fut.result()
                    except Exception as exc:
                        r = {
                            "stable_key": item.stable_key,
                            "source": source,
                            "source_auction_id": str(item.source_auction_id),
                            "ok": False,
                            "error": str(exc),
                        }
                    results.append(r)
                    attempted_ids.append(str(item.source_auction_id))
                    attempted_keys.add(item.stable_key)
                    journal.append(
                        {
                            "stable_key": r.get("stable_key"),
                            "ok": bool(r.get("ok")),
                            "phase": "fetch",
                            "error": r.get("error"),
                            "bytes": r.get("bytes"),
                            "sha": r.get("doc_sha256"),
                        }
                    )
            timing["fetch_s"] += time.monotonic() - t_fetch

            _apply_fetch_failures(ledger, results)
            pending_ok = [r for r in results if r.get("ok")]
            fetch_fail_n = len(results) - len(pending_ok)
            fail_count += fetch_fail_n
            batch_fail += fetch_fail_n
            for r in results:
                if not r.get("ok"):
                    failed_keys.append(str(r["stable_key"]))

            if not pending_ok:
                write_ledger(ledger, ledger_path)
                _pause_between_auctions()
                return batch_ok, batch_fail, failed_keys

            # Batch Hostinger flush + verify
            t_flush = time.monotonic()
            flush_ok, flush_msg, verified = flush_download_files(pending_ok, public_dir=public_dir)
            timing["flush_s"] += time.monotonic() - t_flush
            stats["pdf_hostinger_flush_batches"] = (
                int(stats.get("pdf_hostinger_flush_batches") or 0) + 1
            )
            _phase(f"wave {wave_num} flush: ok={flush_ok} {flush_msg}")

            if not flush_ok:
                stats["pdf_hostinger_flush_failures"] = (
                    int(stats.get("pdf_hostinger_flush_failures") or 0) + 1
                )
                _mark_unverified_pending(
                    ledger,
                    pending_ok,
                    set(),
                    error=f"Hostinger flush failed: {flush_msg}",
                )
                fail_count += len(pending_ok)
                batch_fail += len(pending_ok)
                failed_keys.extend(str(r["stable_key"]) for r in pending_ok)
                write_ledger(ledger, ledger_path)
                return batch_ok, batch_fail, failed_keys

            verified_keys = {str(r["stable_key"]) for r in verified}
            committed = _commit_verified(ledger, verified, stats=stats)
            ok_count += committed
            batch_ok += committed
            for r in verified:
                journal.append(
                    {
                        "stable_key": r["stable_key"],
                        "ok": True,
                        "phase": "flushed",
                        "flushed": True,
                        "path": r.get("hostinger_doc_path"),
                    }
                )

            unverified = [r for r in pending_ok if str(r["stable_key"]) not in verified_keys]
            if unverified:
                _mark_unverified_pending(
                    ledger,
                    unverified,
                    verified_keys,
                    error="Hostinger URL not HTTP 200 after wave flush",
                )
                fail_count += len(unverified)
                batch_fail += len(unverified)
                failed_keys.extend(str(r["stable_key"]) for r in unverified)

            write_ledger(ledger, ledger_path)
            _pause_between_auctions()
            return batch_ok, batch_fail, failed_keys

        for batch_num in range(1, max_batches + 1):
            elapsed_min = (time.monotonic() - loop_t0) / 60.0
            if elapsed_min >= PIPELINE_JOB_TIMEBOX_MIN:
                _phase(f"timebox reached ({elapsed_min:.0f}m); stopping")
                break
            if _unique_attempted() >= run_item_cap:
                _phase(f"max-download cap reached ({run_item_cap})")
                break

            remaining = run_item_cap - _unique_attempted()
            select_n = min(wave_size, remaining)
            selected = select_for_download(
                ledger, limit=select_n, pdf_dir=pdf_dir, source=source
            )
            if not selected:
                _phase(f"download backlog clear after {batch_num - 1} wave(s)")
                break

            # Drop already-done (race with peer)
            work = []
            for item in selected:
                if item.download == "done":
                    skipped_existing += 1
                    continue
                work.append(item)
            if not work:
                continue

            _phase(
                f"wave {batch_num}/{max_batches}: selected={len(work)} "
                f"source={source} workers={workers}"
            )
            batch_ok, batch_fail, failed_keys = _process_wave(work, wave_num=batch_num)

            # Wave-end retries for failed keys only
            retry_rounds = max(0, int(DOWNLOAD_BATCH_RETRY_ROUNDS))
            for retry_round in range(1, retry_rounds + 1):
                if not failed_keys:
                    break
                elapsed_min = (time.monotonic() - loop_t0) / 60.0
                if elapsed_min >= PIPELINE_JOB_TIMEBOX_MIN:
                    break
                by_key = ledger.by_key()
                retry_items = []
                for key in failed_keys:
                    item = by_key.get(key)
                    if item is None or item.download == "done":
                        continue
                    retry_items.append(item)
                if not retry_items:
                    break
                _phase(
                    f"wave {batch_num} retry {retry_round}/{retry_rounds}: n={len(retry_items)}"
                )
                rok, rfail, failed_keys = _process_wave(
                    retry_items, wave_num=batch_num * 1000 + retry_round
                )
                batch_ok += rok
                # fail counts already adjusted inside _process_wave

            stats["batches_completed"] = batch_num
            stats["waves_completed"] = batch_num
            elapsed = max(0.001, time.monotonic() - loop_t0)
            rate = ok_count / (elapsed / 60.0)
            batch_reports.append(
                {
                    "wave": batch_num,
                    "ok": batch_ok,
                    "fail": batch_fail,
                    "retry_left": len(failed_keys),
                    "items_per_min": round(rate, 2),
                }
            )
            _phase(
                f"wave {batch_num} done ok={batch_ok} fail={batch_fail} "
                f"rate={rate:.1f}/min throttle={throttle.snapshot()}"
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

        rate = ok_count / max(0.001, elapsed_min)
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
                "timing": timing,
                "items_per_min": round(rate, 2),
                "throttle": throttle.snapshot(),
                "batches_completed": int(stats.get("batches_completed") or 0),
                "batch_reports": batch_reports,
                "ledger": ledger.status_counts(),
                "warnings": warnings,
                "estimated_runs_to_clear": estimated_download_runs_to_clear(
                    ledger, cap=wave_size, pdf_dir=pdf_dir, source=source
                ),
            }
        )
        (run_dir / "download_report.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
        send_telegram_report(payload, event="download_done")
        status = "Complete" if backlog_left == 0 else "Paused · timebox"
        # Event chain: wake parse when new downloads created eligible work
        parse_eligible = count_parse_eligible(ledger)
        kicked_parse = False
        kick_reason = ""
        if ok_count > 0 and parse_eligible > 0:
            kicked_parse, kick_reason = kick_if_needed(
                "pipeline-parse-assets.yml",
                reason="download_done_parse_eligible",
                backlog=parse_eligible,
            )
            if kicked_parse:
                record_resume(
                    "parse_kick",
                    {"reason": kick_reason, "parse_eligible": parse_eligible, "from": lane_id},
                )
        truth = publish_pipeline_status(
            ledger,
            lane=lane_id,
            wake_reason=kick_reason or ("idle" if parse_eligible == 0 else "cron_or_manual"),
            extra={
                "ok_count": ok_count,
                "parse_kick": kicked_parse,
                "parse_kick_reason": kick_reason,
            },
        )
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
                "items_per_min": round(rate, 2),
                "parse_eligible": parse_eligible,
                "parse_kick": kicked_parse,
                **truth_for_telegram(truth),
            },
            noop=attempted == 0 and backlog_left == 0,
        )
        payload["parse_eligible"] = parse_eligible
        payload["parse_kick"] = kicked_parse
        payload["truth"] = truth_for_telegram(truth)
        _phase(
            f"done ok={ok_count} fail={fail_count} backlog={backlog_left} "
            f"rate={rate:.1f}/min parse_eligible={parse_eligible} kick_parse={kicked_parse} "
            f"fetch_s={timing['fetch_s']:.1f} flush_s={timing['flush_s']:.1f}"
        )
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
    parser.add_argument("--wave-size", type=int, default=DOWNLOAD_WAVE_SIZE)
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
        wave_size=args.wave_size,
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
