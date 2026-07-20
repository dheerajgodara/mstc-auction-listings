"""VPS MSTC download worker: polite portal fetch → R2 verify → ledger done → delete local.

Designed for MIYNU (/opt/mstc-auction-listings). Scratch disk is ephemeral; R2 + Hostinger
ledger are the source of truth. Does not touch /opt/viynu or /opt/mstc-pdf-experiment.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scraper.config import REPO_ROOT
from scraper.download_engine import fetch_mstc_to_local
from scraper.download_flush import flush_download_files
from scraper.download_throttle import DownloadThrottle
from scraper.filters import make_run_id
from scraper.object_store import public_object_url
from scraper.pipeline_ledger import (
    DEFAULT_LEDGER_PATH,
    count_download_pending,
    load_ledger,
    mark_download,
    pull_ledger,
    push_ledger,
    select_for_download,
    write_ledger,
)
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report

logger = logging.getLogger("scraper.vps_mstc_download")

DEFAULT_GAP_SEC = float(os.environ.get("VPS_DOWNLOAD_GAP_SEC", "2"))
DEFAULT_CONCURRENCY = int(os.environ.get("VPS_DOWNLOAD_CONCURRENCY", "2"))
DEFAULT_FAIL_STREAK_ABORT = int(os.environ.get("VPS_DOWNLOAD_FAIL_STREAK_ABORT", "5"))
SCRATCH_ROOT = REPO_ROOT / "work" / "download_scratch"
LOCK_PATH = REPO_ROOT / "work" / "vps_mstc_download.lock"


def _phase(msg: str) -> None:
    line = f"[vps_mstc_download] {msg}"
    print(line, flush=True)
    logger.info(msg)


def _cdn_url_for_aid(aid: str) -> str:
    rel = f"pdfs/{aid}.pdf"
    return public_object_url(rel) or f"https://files.csmg.in/{rel}"


def cdn_already_ok(aid: str) -> bool:
    """True when catalogue PDF is already publicly reachable on CDN with PDF magic."""
    import requests

    url = _cdn_url_for_aid(aid)
    try:
        resp = requests.get(
            url,
            timeout=20,
            allow_redirects=True,
            headers={
                "Range": "bytes=0-15",
                "User-Agent": "Mozilla/5.0 MSTC-MediaVerify/1.0",
            },
        )
        body = resp.content or b""
        ok = resp.status_code in (200, 206) and body.startswith(b"%PDF")
        resp.close()
        return ok
    except Exception:
        return False


def delete_local_pdfs(paths: list[Path]) -> int:
    """Remove scratch/public PDFs after durable R2+ledger commit. Returns deleted count."""
    n = 0
    for p in paths:
        try:
            if p.is_file():
                p.unlink()
                n += 1
        except OSError as exc:
            logger.warning("delete failed %s: %s", p, exc)
    return n


def should_abort_fail_streak(consecutive_fail: int, *, threshold: int = DEFAULT_FAIL_STREAK_ABORT) -> bool:
    return consecutive_fail >= max(1, int(threshold))


def run_vps_mstc_download(
    *,
    max_download: int = 150,
    gap_sec: float = DEFAULT_GAP_SEC,
    concurrency: int = DEFAULT_CONCURRENCY,
    fail_streak_abort: int = DEFAULT_FAIL_STREAK_ABORT,
    break_stale_lock: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    run_id = f"vps_mstc_{make_run_id()}"
    scratch = SCRATCH_ROOT
    pdf_dir = scratch / "pdfs"
    public_dir = scratch / "public"
    raw_dir = scratch / "raw"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "pdfs").mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    acquire_refresh_lock(
        lock_path=LOCK_PATH,
        run_id=run_id,
        stale_minutes=180,
        break_stale_lock=break_stale_lock,
    )

    ledger_path = DEFAULT_LEDGER_PATH
    downloaded = 0
    failed = 0
    skipped_cdn = 0
    aborted_health = False
    consecutive_fail = 0
    t0 = time.monotonic()
    warnings: list[str] = []

    try:
        pulled = pull_ledger(local_path=ledger_path, require=True)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError("ledger pull failed and local ledger empty")

        selected = select_for_download(
            ledger,
            limit=max(1, int(max_download)),
            pdf_dir=pdf_dir,
            source="mstc",
        )
        pending_before = count_download_pending(ledger, source="mstc")
        _phase(
            f"start run_id={run_id} selected={len(selected)} "
            f"pending_mstc={pending_before} gap={gap_sec}s concurrency={concurrency}"
        )
        if dry_run:
            return {
                "run_id": run_id,
                "status": "dry_run",
                "selected": len(selected),
                "pending_mstc": pending_before,
            }

        throttle = DownloadThrottle()
        # Soften adaptive throttle for VPS polite pacing (gap handles politeness).
        os.environ.setdefault("DOWNLOAD_THROTTLE_MIN_SEC", "0.05")

        workers = max(1, min(int(concurrency), 8))
        i = 0
        while i < len(selected):
            if should_abort_fail_streak(consecutive_fail, threshold=fail_streak_abort):
                aborted_health = True
                warnings.append(f"health gate: {consecutive_fail} consecutive fails — aborting wave")
                _phase(warnings[-1])
                break

            batch = selected[i : i + workers]
            i += len(batch)

            # Idempotent CDN hits first (no portal fetch).
            fetch_batch: list[Any] = []
            pending_flush: list[dict[str, Any]] = []
            for item in batch:
                aid = str(item.source_auction_id)
                rel = f"pdfs/{aid}.pdf"
                if cdn_already_ok(aid):
                    mark_download(
                        ledger,
                        item.stable_key,
                        ok=True,
                        hostinger_doc_path=rel,
                        object_doc_url=_cdn_url_for_aid(aid),
                    )
                    skipped_cdn += 1
                    downloaded += 1
                    consecutive_fail = 0
                    _phase(f"cdn-hit {item.stable_key}")
                    continue
                fetch_batch.append(item)

            if fetch_batch:
                if gap_sec > 0 and (downloaded + failed) > 0:
                    time.sleep(gap_sec)

                results: list[dict[str, Any]] = []
                with ThreadPoolExecutor(max_workers=min(workers, len(fetch_batch))) as pool:
                    futs = {
                        pool.submit(
                            fetch_mstc_to_local,
                            item=item,
                            pdf_dir=pdf_dir,
                            public_dir=public_dir,
                            raw_dir=raw_dir,
                            skip_pdf=False,
                            stats={},
                            throttle=throttle,
                        ): item
                        for item in fetch_batch
                    }
                    for fut in as_completed(futs):
                        results.append(fut.result())

                for r in results:
                    sk = r["stable_key"]
                    if not r.get("ok"):
                        failed += 1
                        consecutive_fail += 1
                        mark_download(ledger, sk, ok=False, error=str(r.get("error") or "fetch failed"))
                        _phase(f"fail {sk}: {r.get('error')}")
                        continue
                    consecutive_fail = 0
                    pending_flush.append(r)

            if pending_flush:
                flush_ok, flush_msg, verified = flush_download_files(
                    pending_flush, public_dir=public_dir
                )
                _phase(f"flush: ok={flush_ok} {flush_msg}")
                verified_keys = {v["stable_key"] for v in verified}
                to_delete: list[Path] = []
                for v in verified:
                    mark_download(
                        ledger,
                        v["stable_key"],
                        ok=True,
                        hostinger_doc_path=v.get("hostinger_doc_path"),
                        object_doc_url=v.get("object_doc_url"),
                        doc_sha256=v.get("doc_sha256"),
                        raw_html_path=v.get("raw_html_path"),
                        local_doc_path=None,
                    )
                    downloaded += 1
                    local = Path(str(v.get("local_path") or ""))
                    if local.is_file():
                        to_delete.append(local)
                    aid = str(v.get("source_auction_id") or "")
                    if aid:
                        alt = pdf_dir / f"{aid}.pdf"
                        if alt.is_file() and alt not in to_delete:
                            to_delete.append(alt)

                for r in pending_flush:
                    if r["stable_key"] in verified_keys:
                        continue
                    failed += 1
                    consecutive_fail += 1
                    mark_download(
                        ledger,
                        r["stable_key"],
                        ok=False,
                        error=f"R2/CDN verify failed: {flush_msg}",
                        local_doc_path=str(r.get("local_path") or "") or None,
                    )

                write_ledger(ledger, ledger_path)
                if not push_ledger(local_path=ledger_path):
                    raise RuntimeError("ledger push failed after successful R2 verify")
                deleted = delete_local_pdfs(to_delete)
                _phase(f"committed {len(verified)} deleted_local={deleted}")

            # Persist CDN-only marks too.
            if skipped_cdn and not pending_flush:
                write_ledger(ledger, ledger_path)
                push_ledger(local_path=ledger_path)

            if should_abort_fail_streak(consecutive_fail, threshold=fail_streak_abort):
                aborted_health = True
                warnings.append(f"health gate: {consecutive_fail} consecutive fails — aborting wave")
                _phase(warnings[-1])
                break

        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)
        pending_after = count_download_pending(load_ledger(ledger_path), source="mstc")
        wall = time.monotonic() - t0
        status = "aborted_health" if aborted_health else "success"
        payload = {
            "run_id": run_id,
            "status": status,
            "downloaded": downloaded,
            "failed": failed,
            "skipped_cdn": skipped_cdn,
            "pending_mstc_before": pending_before,
            "pending_mstc_after": pending_after,
            "wall_seconds": round(wall, 1),
            "warnings": warnings,
        }
        send_lane_report(
            "download_mstc",
            "finished",
            {
                "downloaded": downloaded,
                "failed": failed,
                "still_need_files": pending_after,
                "wall_seconds": wall,
            },
            noop=downloaded == 0 and failed == 0,
        )
        _phase(
            f"done status={status} ok={downloaded} fail={failed} "
            f"cdn_hit={skipped_cdn} pending={pending_after} wall={wall:.1f}s"
        )
        return payload
    except Exception as exc:
        logger.exception("vps mstc download failed")
        send_lane_report("download_mstc", "failed", {"error": str(exc)})
        raise
    finally:
        release_refresh_lock(LOCK_PATH, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="VPS MSTC polite download → R2 → ledger")
    p.add_argument("--max-download", type=int, default=150)
    p.add_argument("--gap-sec", type=float, default=DEFAULT_GAP_SEC)
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("--fail-streak-abort", type=int, default=DEFAULT_FAIL_STREAK_ABORT)
    p.add_argument("--break-stale-lock", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    run_vps_mstc_download(
        max_download=args.max_download,
        gap_sec=args.gap_sec,
        concurrency=args.concurrency,
        fail_streak_abort=args.fail_streak_abort,
        break_stale_lock=args.break_stale_lock,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
