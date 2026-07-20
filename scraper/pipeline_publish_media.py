"""Publish lane: flush fetched_local docs to R2 (optional) + Hostinger → download=done.

Decouples portal fetch from Hostinger SSH so download backlog can drain even when
Hostinger is flaky (Phase B). Kick from download lane or cron.
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
from scraper.object_store import r2_configured, upload_hostinger_rel
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
        # Relative to repo
        cand = REPO_ROOT / raw
        if cand.is_file():
            return cand
    rel = (getattr(item, "hostinger_doc_path", None) or "").strip().lstrip("/")
    if rel:
        cand = public_dir / rel
        if cand.is_file():
            return cand
        # MSTC convention
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
        clear_stale_control_sockets()
        ok_pf, pf_msg = preflight_hostinger()
        _phase(pf_msg)
        if not ok_pf:
            send_lane_report(
                "publish_media",
                "failed",
                {"error": f"Hostinger preflight failed: {pf_msg}", "github_run_url": _github_run_url()},
            )
            raise RuntimeError(f"Hostinger preflight failed: {pf_msg}")

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
                    # Infer relative path under public/
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

                object_url = None
                if r2_configured():
                    up = upload_hostinger_rel(local, rel)
                    if up.get("ok"):
                        object_url = up.get("url")
                    else:
                        _phase(f"R2 upload warn {item.stable_key}: {up.get('error')}")

                flush_items.append(
                    {
                        "stable_key": item.stable_key,
                        "hostinger_doc_path": rel,
                        "local_path": local,
                        "raw_html_path": item.raw_html_path,
                        "doc_sha256": item.doc_sha256,
                        "object_doc_url": object_url,
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
                    hostinger_doc_url=str(v["hostinger_doc_url"]),
                    doc_sha256=v.get("doc_sha256"),
                    raw_html_path=v.get("raw_html_path"),
                    local_doc_path=str(v.get("local_path") or ""),
                    object_doc_url=v.get("object_doc_url")
                    or by_key.get(str(v["stable_key"]), {}).get("object_doc_url"),
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

        publish_pipeline_status(
            lane="publish_media",
            wake_reason="complete",
            ledger=ledger,
            extra={"published": ok_count, "failed": fail_count, "remaining": remaining},
        )
        status = "success" if fail_count == 0 or ok_count > 0 else "failed"
        send_lane_report(
            "publish_media",
            status,
            {
                "ok_count": ok_count,
                "fail_count": fail_count,
                "ready for site": remaining,
                "github_run_url": _github_run_url(),
                "site_base_url": SITE_BASE_URL,
            },
        )
        return {
            "run_id": run_id,
            "status": status,
            "ok_count": ok_count,
            "fail_count": fail_count,
            "remaining": remaining,
            "parse_kick": kicked_parse,
        }
    except Exception as exc:
        logger.exception("publish_media failed")
        send_lane_report(
            "publish_media",
            "failed",
            {"error": str(exc), "github_run_url": _github_run_url()},
        )
        raise
    finally:
        release_refresh_lock(lock_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish fetched_local docs to Hostinger/R2")
    ap.add_argument("--source", default=None, help="mstc | gem_forward | omit for all")
    ap.add_argument("--wave-size", type=int, default=50)
    ap.add_argument("--max-waves", type=int, default=40)
    ap.add_argument("--break-stale-lock", action="store_true")
    args = ap.parse_args()
    run_publish_media(
        source=args.source,
        wave_size=args.wave_size,
        max_waves=args.max_waves,
        break_stale_lock=args.break_stale_lock,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
