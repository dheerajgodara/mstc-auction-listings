#!/usr/bin/env python3
"""Send the daily catalogue Telegram digest (IST morning).

Pulls Hostinger pipeline_status.json when SSH is configured; otherwise uses
optional CLI overrides / empty snapshot (still sends All clear heartbeat).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper.pipeline_markers import pull_pipeline_json
from scraper.pipeline_status import STATUS_NAME
from scraper.telegram_reporter import _ist_now_short, send_daily_digest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("telegram_daily_digest")


def _snapshot_from_status(status: dict | None) -> dict:
    status = status or {}
    failed = int(status.get("failed_yesterday") or (status.get("extra") or {}).get("failed") or 0)
    return {
        "when": _ist_now_short(),
        "live_on_site": int(status.get("live_export_count") or status.get("live_on_site") or 0),
        "ready_for_site": int(status.get("publishable_future") or status.get("ready_for_site") or 0),
        "still_need_files": int(status.get("download_pending") or status.get("still_need_files") or 0),
        "downloaded_yesterday": int(status.get("downloaded_yesterday") or 0),
        "processed_yesterday": int(status.get("processed_yesterday") or 0),
        "failed_yesterday": failed,
        "all_clear": failed == 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send daily Telegram catalogue digest")
    parser.add_argument("--dry-run", action="store_true", help="Print message; do not send")
    args = parser.parse_args(argv)

    status = pull_pipeline_json(STATUS_NAME)
    if status is None:
        logger.warning("pipeline_status.json unavailable; sending inventory-empty digest")
    snapshot = _snapshot_from_status(status)

    if args.dry_run:
        from scraper.telegram_reporter import build_daily_digest_message

        print(build_daily_digest_message(snapshot))
        return 0

    ok = send_daily_digest(snapshot)
    if not ok:
        logger.error("telegram digest send failed (missing credentials or API error)")
        return 1
    logger.info("daily digest sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
