"""Publish lane: flush fetched_local docs to R2 CDN → download=done.

Decouples portal fetch from Hostinger SSH so download backlog can drain even when
Hostinger is flaky. Media durability is R2-only (files.scrapauctionindia.com).
Ledger pull/push may still use Hostinger for private pipeline state.
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

from scraper.config import (
    DEFAULT_PIPELINE_LEDGER,
    PIPELINE_JOB_TIMEBOX_MIN,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.download_flush import flush_download_files
from scraper.filters import make_run_id
from scraper.hostinger_ssh import clear_stale_control_sockets, preflight_hostinger, push_heartbeat
from scraper.lane_resume import kick_if_needed
from scraper.object_store import media_r2_only, r2_configured
from scraper.pipeline_ledger import (
    load_ledger,
    mark_download,
    pull_ledger,
    push_ledger,
    select_for_publish,
    write_ledger,
)
from scraper.pipeline_status import publish_pipeline_status
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_publish_media")


def _phase(msg: str) -> None:
    print(f"[publish_media] {msg}", flush=True)
    logger.info(msg)


def _setup_logging(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(run_dir / "publish_media.log", encoding="utf-8"),
        ],
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


def _resolve_local(item: Any, public_dir: Path) -> Path | None:
    raw = (getattr(item, "local_doc_path", None) or "").strip()
    if raw:
        p = Path(raw)
        if p.is_file():
            return p
        cand = REPO_ROOT / raw
        if cand.is_file():
            return cand
    rel = (getattr(item, "hostinger_doc_path", None) or "").strip().lstrip("/")
    if rel:
        cand = public_dir / rel
        if cand.is_file():
            return cand
        aid = str(getattr(item, "source_auction_id", "") or "")
        if aid and (public_dir / "pdfs" / f"{aid}.pdf").is_file():
            return public_dir / "pdfs" / f"{aid}.pdf"
        if aid and (public_dir / "docs" / "gem" / f"{aid}.pdf").is_file():
            return public_dir / "docs" / "gem" / f"{aid}.pdf"
    return None


def run_publish_media(
    *,
    repo_root: Path = REPO_ROOT,
    source: str | None = None,
    wave_size: int = 50,
    max_waves: int = 40,
    break_stale_lock: bool = True,
) -> dict[str, Any]:
    run_id = f"publish_media_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)
    lock_path = repo_root / "work" / "publish_media.lock"
    acquire_refresh_lock(
        lock_path=lock_path,
        run_id=run_id,
        stale_minutes=120,
        break_stale_lock=break_stale_lock,
    )

    public_dir = repo_root / "web" / "public"
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    t0 = time.monotonic()
    started = datetime.now(IST).isoformat()
    ok_count = 0
    fail_count = 0
    try:
        if not r2_configured():
            raise RuntimeError("R2 not configured — set R2_* secrets for media publish")
        _phase(
            f"R2 media publish mode={'r2_only' if media_r2_only() else 'r2'} "
            f"cdn configured={bool(r2_configured())}"
        )

        clear_stale_control_sockets()
        # Ledger still lives on Hostinger; preflight is best-effort for ledger sync.
        ok_pf, pf_msg = preflight_hostinger()
        _phase(pf_msg)
        if not ok_pf:
            _phase(f"Hostinger preflight soft-fail (ledger sync may use local): {pf_msg}")

        pulled = pull_ledger(local_path=ledger_path)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError("ledger pull failed and local ledger empty")

        for wave in range(1, max_waves + 1):
            if (time.monotonic() - t0) / 60.0 >= PIPELINE_JOB_TIMEBOX_MIN:
                _phase("timebox reached")
                break
            selected = select_for_publish(ledger, limit=wave_size, source=source)
            if not selected:
                _phase(f"publish queue empty after {wave - 1} wave(s)")
                break

            flush_items: list[dict[str, Any]] = []
            for item in selected:
                local = _resolve_local(item, public_dir)
                rel = (item.hostinger_doc_path or "").strip()
                if not rel and local:
                    try:
                        rel = str(local.resolve().relative_to(public_dir.resolve())).replace(
                            "\\", "/"
                        )
                    except ValueError:
                        rel = f"pdfs/{item.source_auction_id}.pdf"
                if not local or not rel:
                    mark_download(
                        ledger,
                        item.stable_key,
                        ok=False,
                        error="publish: local file missing",
                        local_doc_path=item.local_doc_path,
                    )
                    fail_count += 1
                    continue

                flush_items.append(
                    {
                        "stable_key": item.stable_key,
                        "hostinger_doc_path": rel,
                        "local_path": local,
                        "raw_html_path": item.raw_html_path,
                        "doc_sha256": item.doc_sha256,
                    }
                )

            if not flush_items:
                write_ledger(ledger, ledger_path)
                continue

            flush_ok, flush_msg, verified = flush_download_files(
                flush_items, public_dir=public_dir
            )
            _phase(f"wave {wave} flush: ok={flush_ok} {flush_msg}")
            verified_keys = {str(v["stable_key"]) for v in verified}
            by_key = {str(x["stable_key"]): x for x in flush_items}

            for v in verified:
                mark_download(
                    ledger,
                    str(v["stable_key"]),
                    ok=True,
                    hostinger_doc_path=str(v["hostinger_doc_path"]),
                    hostinger_doc_url=str(v.get("hostinger_doc_url") or v.get("object_doc_url") or ""),
                    doc_sha256=v.get("doc_sha256"),
                    raw_html_path=v.get("raw_html_path"),
                    local_doc_path=str(v.get("local_path") or ""),
                    object_doc_url=str(
                        v.get("object_doc_url")
                        or by_key.get(str(v["stable_key"]), {}).get("object_doc_url")
                        or v.get("hostinger_doc_url")
                        or ""
                    ),
                    content_changed=True,
                )
                ok_count += 1

            for it in flush_items:
                if str(it["stable_key"]) in verified_keys:
                    continue
                mark_download(
                    ledger,
                    str(it["stable_key"]),
                    ok=False,
                    error=f"publish flush incomplete: {flush_msg}",
                    local_doc_path=str(it.get("local_path") or ""),
                )
                fail_count += 1

            write_ledger(ledger, ledger_path)
            push_ledger(local_path=ledger_path)
            push_heartbeat(
                {
                    "lane": "publish_media",
                    "wave": wave,
                    "ok": ok_count,
                    "fail": fail_count,
                    "pending_publish": len(
                        select_for_publish(ledger, limit=10**9, source=source)
                    ),
                }
            )

        remaining = len(select_for_publish(ledger, limit=10**9, source=source))
        kicked_parse = False
        if ok_count > 0:
            kicked_parse, _ = kick_if_needed(
                "pipeline-parse-assets.yml",
                reason="publish_media_done",
                backlog=ok_count,
            )

        report = {
            "ok_count": ok_count,
            "fail_count": fail_count,
            "downloaded": ok_count,
            "failed": fail_count,
            "ready_for_site": remaining,
            "remaining": remaining,
            "github_run_url": _github_run_url(),
            "site_base_url": SITE_BASE_URL,
            "started_at": started,
            "elapsed_sec": round(time.monotonic() - t0, 1),
            "kick_parse": kicked_parse,
        }
        send_lane_report("publish_media", "completed" if fail_count == 0 else "partial", report)
        publish_pipeline_status(
            ledger,
            lane="publish_media",
            wake_reason="publish_complete",
            extra=report,
        )
        (run_dir / "summary.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        _phase(f"done ok={ok_count} fail={fail_count} remaining={remaining}")
        return report
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish fetched_local media to R2 CDN")
    parser.add_argument("--source", default="", help="mstc | gem_forward | empty=all")
    parser.add_argument("--wave-size", type=int, default=50)
    parser.add_argument("--max-waves", type=int, default=40)
    parser.add_argument("--break-stale-lock", action="store_true")
    args = parser.parse_args(argv)
    src = (args.source or "").strip() or None
    run_publish_media(
        source=src,
        wave_size=max(1, int(args.wave_size)),
        max_waves=max(1, int(args.max_waves)),
        break_stale_lock=bool(args.break_stale_lock),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
