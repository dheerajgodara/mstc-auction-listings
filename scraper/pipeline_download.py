"""Fast download lane: parallel portal fetch → batch Hostinger flush → HTTP-200 → done."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
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
    DOWNLOAD_DECOUPLE_FLUSH,
    DOWNLOAD_FAIL_BUDGET_ABS,
    DOWNLOAD_FAIL_BUDGET_PCT,
    DOWNLOAD_FETCH_TIMEOUT_SEC,
    DOWNLOAD_STALL_ABORT_MIN,
    DOWNLOAD_STREAM_FLUSH_EVERY,
    DOWNLOAD_SUCCESS_PAUSE_SEC,
    DOWNLOAD_WAVE_DEADLINE_SEC,
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
from scraper.hostinger_ssh import (
    clear_stale_control_sockets,
    preflight_hostinger,
    push_heartbeat,
)
from scraper.lane_resume import dispatch_workflow, kick_if_needed, record_resume, should_self_resume
from scraper.media_sync import media_push_required
from scraper.pipeline_ledger import (
    count_parse_eligible,
    estimated_download_runs_to_clear,
    fail_budget_ok,
    load_ledger,
    mark_download,
    mark_download_fetched_local,
    pull_ledger,
    push_ledger,
    select_for_download,
    select_for_publish,
    write_ledger,
)
from scraper.pipeline_status import publish_pipeline_status, truth_for_telegram
from scraper.raw_store import _hostinger_ssh_config, pull_public_pdf_files
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report

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
        rel = str(r.get("hostinger_doc_path") or "")
        local = Path(str(r.get("local_path") or ""))
        if rel.startswith("docs/gem/"):
            from scraper.gem_doc_validate import classify_local_gem_file

            ok, _kind, err = classify_local_gem_file(local)
            if not ok:
                mark_download(
                    ledger,
                    str(r["stable_key"]),
                    ok=False,
                    error=err or "gem_html_rejected",
                    raw_html_path=r.get("raw_html_path"),
                )
                continue
        mark_download(
            ledger,
            str(r["stable_key"]),
            ok=True,
            hostinger_doc_path=str(r["hostinger_doc_path"]),
            hostinger_doc_url=str(r.get("hostinger_doc_url") or r.get("object_doc_url") or ""),
            object_doc_url=str(r.get("object_doc_url") or r.get("hostinger_doc_url") or ""),
            doc_sha256=r.get("doc_sha256"),
            raw_html_path=r.get("raw_html_path"),
            local_doc_path=str(r.get("local_path") or ""),
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

    warnings: list[str] = []
    errors: list[str] = []
    skipped_existing = 0
    timing = {"fetch_s": 0.0, "flush_s": 0.0}
    last_progress_at = time.monotonic()
    try:
        clear_stale_control_sockets()
        from scraper.hostinger_ssh import hostinger_ssh_config as _live_ssh_cfg

        ok_pf, pf_msg = preflight_hostinger()
        _phase(pf_msg)
        # Hard-fail only when SSH is required. MEDIA_R2_ONLY + R2 → soft-fail (ledger best-effort).
        if not ok_pf and _live_ssh_cfg() is not None:
            from scraper.object_store import media_r2_only, r2_configured

            if media_r2_only() and r2_configured():
                _phase(f"Hostinger preflight soft-fail (MEDIA_R2_ONLY): {pf_msg}")
                warnings.append(f"Hostinger preflight soft-fail: {pf_msg}")
            else:
                send_lane_report(
                    lane_id,
                    "failed",
                    {
                        "error": f"Hostinger stalled (preflight): {pf_msg}",
                        "github_run_url": _github_run_url(),
                    },
                )
                raise RuntimeError(f"Hostinger preflight failed: {pf_msg}")

        if media_push_required() and _hostinger_ssh_config() is None:
            from scraper.object_store import media_r2_only, r2_configured

            if not (media_r2_only() and r2_configured()):
                raise RuntimeError(
                    "download requires Hostinger SSH (HOSTINGER_*) when MEDIA_PUSH_REQUIRED=1 "
                    "unless MEDIA_R2_ONLY=1 with R2 configured"
                )
            _phase("MEDIA_R2_ONLY: Hostinger SSH optional for media (ledger sync may still use it)")

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
        gem_lock = threading.Lock()
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
            # Shared GemForwardClient is not thread-safe — serialize portal I/O.
            with gem_lock:
                return fetch_gem_to_local(
                    item=item,
                    raw_dir=raw_dir,
                    public_dir=public_dir,
                    client=gem_client,
                    throttle=throttle,
                )

        def _flush_pending(pending_ok: list[dict[str, Any]], *, wave_num: int) -> tuple[int, int, list[str]]:
            nonlocal ok_count, fail_count, last_progress_at
            batch_ok = 0
            batch_fail = 0
            failed_keys: list[str] = []
            if not pending_ok:
                return batch_ok, batch_fail, failed_keys

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
                if DOWNLOAD_DECOUPLE_FLUSH:
                    for r in pending_ok:
                        mark_download_fetched_local(
                            ledger,
                            str(r["stable_key"]),
                            local_doc_path=str(r.get("local_path") or ""),
                            hostinger_doc_path=str(r.get("hostinger_doc_path") or ""),
                            doc_sha256=r.get("doc_sha256"),
                            raw_html_path=r.get("raw_html_path"),
                        )
                        journal.append(
                            {
                                "stable_key": r["stable_key"],
                                "ok": True,
                                "phase": "fetched_local",
                                "local_path": str(r.get("local_path") or ""),
                                "error": flush_msg,
                            }
                        )
                    _phase(
                        f"wave {wave_num}: R2 flush failed — staged "
                        f"{len(pending_ok)} as fetched_local for publish lane"
                    )
                    write_ledger(ledger, ledger_path)
                    return batch_ok, batch_fail, failed_keys
                _mark_unverified_pending(
                    ledger,
                    pending_ok,
                    set(),
                    error=f"R2 flush failed: {flush_msg}",
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
            if committed:
                last_progress_at = time.monotonic()
            for r in verified:
                journal.append(
                    {
                        "stable_key": r["stable_key"],
                        "ok": True,
                        "phase": "flushed",
                        "flushed": True,
                        "path": r.get("hostinger_doc_path"),
                        "local_path": str(r.get("local_path") or ""),
                    }
                )

            unverified = [r for r in pending_ok if str(r["stable_key"]) not in verified_keys]
            if unverified:
                if DOWNLOAD_DECOUPLE_FLUSH:
                    for r in unverified:
                        mark_download_fetched_local(
                            ledger,
                            str(r["stable_key"]),
                            local_doc_path=str(r.get("local_path") or ""),
                            hostinger_doc_path=str(r.get("hostinger_doc_path") or ""),
                            doc_sha256=r.get("doc_sha256"),
                            raw_html_path=r.get("raw_html_path"),
                        )
                else:
                    _mark_unverified_pending(
                        ledger,
                        unverified,
                        verified_keys,
                        error="CDN URL not HTTP 200 after wave flush",
                    )
                    fail_count += len(unverified)
                    batch_fail += len(unverified)
                    failed_keys.extend(str(r["stable_key"]) for r in unverified)

            write_ledger(ledger, ledger_path)
            return batch_ok, batch_fail, failed_keys

        def _process_wave(selected: list[Any], *, wave_num: int) -> tuple[int, int, list[str]]:
            nonlocal ok_count, fail_count, last_progress_at
            from concurrent.futures import wait, FIRST_COMPLETED

            batch_ok = 0
            batch_fail = 0
            failed_keys: list[str] = []
            wave_deadline = time.monotonic() + max(60.0, float(DOWNLOAD_WAVE_DEADLINE_SEC))
            fetch_timeout = max(30.0, float(DOWNLOAD_FETCH_TIMEOUT_SEC))
            stream_every = max(0, int(DOWNLOAD_STREAM_FLUSH_EVERY))

            if source == "mstc" and not skip_pdf:
                pdf_names = [f"{i.source_auction_id}.pdf" for i in selected]
                pull_result = pull_public_pdf_files(
                    public_dir=public_dir, filenames=pdf_names, timeout_sec=90, attempts=2
                )
                if pull_result.warnings:
                    warnings.extend(pull_result.warnings[:5])

            t_fetch = time.monotonic()
            results: list[dict[str, Any]] = []
            pending_stream: list[dict[str, Any]] = []
            flushed_keys: set[str] = set()

            with ThreadPoolExecutor(max_workers=min(workers, len(selected))) as pool:
                futs: dict = {}
                for item in selected:
                    resume = journal.local_resume_path(item.stable_key)
                    if resume is not None:
                        if source == "mstc":
                            rel = f"pdfs/{item.source_auction_id}.pdf"
                        else:
                            rel = f"docs/gem/{item.source_auction_id}.pdf"
                            for cand in (
                                public_dir / "docs" / "gem" / f"{item.source_auction_id}.pdf",
                                public_dir / "docs" / "gem" / f"{item.source_auction_id}.html",
                            ):
                                if cand.is_file():
                                    resume = cand
                                    try:
                                        rel = str(cand.relative_to(public_dir)).replace("\\", "/")
                                    except ValueError:
                                        pass
                                    break
                        r = {
                            "stable_key": item.stable_key,
                            "source": source,
                            "source_auction_id": str(item.source_auction_id),
                            "ok": True,
                            "local_path": resume,
                            "hostinger_doc_path": rel,
                            "doc_sha256": (journal.latest_ok_fetch(item.stable_key) or {}).get("sha"),
                            "resumed": True,
                        }
                        results.append(r)
                        attempted_ids.append(str(item.source_auction_id))
                        attempted_keys.add(item.stable_key)
                        journal.append(
                            {
                                "stable_key": r["stable_key"],
                                "ok": True,
                                "phase": "fetch",
                                "resumed": True,
                                "local_path": str(resume),
                                "sha": r.get("doc_sha256"),
                            }
                        )
                        continue
                    futs[pool.submit(_fetch_one, item)] = item

                pending_futs = set(futs)
                while pending_futs:
                    if time.monotonic() >= wave_deadline:
                        _phase(
                            f"wave {wave_num}: deadline reached — abandoning "
                            f"{len(pending_futs)} in-flight fetch(es)"
                        )
                        for fut in list(pending_futs):
                            item = futs[fut]
                            results.append(
                                {
                                    "stable_key": item.stable_key,
                                    "source": source,
                                    "source_auction_id": str(item.source_auction_id),
                                    "ok": False,
                                    "error": "wave_deadline",
                                }
                            )
                            attempted_ids.append(str(item.source_auction_id))
                            attempted_keys.add(item.stable_key)
                            failed_keys.append(item.stable_key)
                        break
                    wait_s = min(5.0, max(0.1, wave_deadline - time.monotonic()))
                    done, pending_futs = wait(
                        pending_futs, timeout=wait_s, return_when=FIRST_COMPLETED
                    )
                    for fut in done:
                        item = futs[fut]
                        try:
                            r = fut.result(timeout=fetch_timeout)
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
                                "local_path": str(r.get("local_path") or ""),
                            }
                        )
                        if r.get("ok") and stream_every > 0:
                            pending_stream.append(r)
                            if len(pending_stream) >= stream_every:
                                bok, bfail, fkeys = _flush_pending(
                                    list(pending_stream), wave_num=wave_num
                                )
                                flushed_keys.update(str(x["stable_key"]) for x in pending_stream)
                                batch_ok += bok
                                batch_fail += bfail
                                failed_keys.extend(fkeys)
                                pending_stream.clear()

            timing["fetch_s"] += time.monotonic() - t_fetch

            _apply_fetch_failures(ledger, results)
            pending_ok = [
                r
                for r in results
                if r.get("ok") and str(r["stable_key"]) not in flushed_keys
            ]
            fetch_fail_n = sum(1 for r in results if not r.get("ok"))
            fail_count += fetch_fail_n
            batch_fail += fetch_fail_n
            for r in results:
                if not r.get("ok"):
                    failed_keys.append(str(r["stable_key"]))

            if pending_stream:
                pending_ok = pending_stream + [
                    r for r in pending_ok if str(r["stable_key"]) not in {
                        str(x["stable_key"]) for x in pending_stream
                    }
                ]

            if pending_ok:
                bok, bfail, fkeys = _flush_pending(pending_ok, wave_num=wave_num)
                batch_ok += bok
                batch_fail += bfail
                failed_keys.extend(fkeys)

            _pause_between_auctions()
            return batch_ok, batch_fail, failed_keys

        for batch_num in range(1, max_batches + 1):
            elapsed_min = (time.monotonic() - loop_t0) / 60.0
            if elapsed_min >= PIPELINE_JOB_TIMEBOX_MIN:
                _phase(f"timebox reached ({elapsed_min:.0f}m); stopping")
                break
            stall_min = (time.monotonic() - last_progress_at) / 60.0
            if (
                stall_min >= float(DOWNLOAD_STALL_ABORT_MIN)
                and ok_count == 0
                and _unique_attempted() > 0
            ):
                msg = (
                    f"download stalled: 0 commits after {stall_min:.0f}m "
                    f"(threshold {DOWNLOAD_STALL_ABORT_MIN}m)"
                )
                _phase(msg)
                send_lane_report(
                    lane_id,
                    "failed",
                    {
                        "error": msg,
                        "github_run_url": _github_run_url(),
                        "still_need_files": eligible_n,
                    },
                )
                raise RuntimeError(msg)
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
            push_heartbeat(
                {
                    "lane": lane_id,
                    "wave": batch_num,
                    "ok": ok_count,
                    "fail": fail_count,
                    "flush_s": round(timing["flush_s"], 1),
                    "fetch_s": round(timing["fetch_s"], 1),
                    "items_per_min": round(rate, 2),
                    "throttle": throttle.snapshot(),
                }
            )

        backlog_left = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir, source=source))
        publish_left = len(select_for_publish(ledger, limit=10**9, source=source))
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
                "publish_left": publish_left,
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
        # Event chain: wake publish for fetched_local, then parse for done downloads
        kicked_publish = False
        if publish_left > 0:
            kicked_publish, pub_reason = kick_if_needed(
                "pipeline-publish-media.yml",
                reason="download_fetched_local",
                backlog=publish_left,
            )
            if kicked_publish:
                record_resume(
                    "publish_kick",
                    {"reason": pub_reason, "publish_left": publish_left, "from": lane_id},
                )
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
                "publish_kick": kicked_publish,
                "publish_left": publish_left,
                "parse_kick_reason": kick_reason,
            },
        )
        # Lane report only (human vocabulary; no dual event telegram).
        send_lane_report(
            lane_id,
            "finished",
            {
                "downloaded": ok_count,
                "failed": fail_count,
                "still_need_files": int(truth.get("download_pending") or backlog_left),
                "ready_to_process": int(truth.get("parse_eligible") or parse_eligible),
                "ready_for_site": publish_left,
                "live_on_site": truth.get("live_export_count"),
            },
            noop=attempted == 0 and backlog_left == 0 and publish_left == 0,
        )
        payload["parse_eligible"] = parse_eligible
        payload["parse_kick"] = kicked_parse
        payload["publish_kick"] = kicked_publish
        payload["truth"] = truth_for_telegram(truth)
        _phase(
            f"done ok={ok_count} fail={fail_count} backlog={backlog_left} "
            f"publish_left={publish_left} rate={rate:.1f}/min "
            f"parse_eligible={parse_eligible} kick_parse={kicked_parse} "
            f"kick_publish={kicked_publish} "
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
        send_lane_report(lane_id, "failed", {"error": str(exc)})
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
