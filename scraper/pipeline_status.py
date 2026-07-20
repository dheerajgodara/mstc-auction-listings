"""Hostinger pipeline_status.json — ledger-truth backlog for operators."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from scraper.pipeline_ledger import PipelineLedger, pipeline_truth_snapshot
from scraper.pipeline_markers import push_pipeline_json

logger = logging.getLogger("scraper.pipeline_status")
IST = ZoneInfo("Asia/Kolkata")

STATUS_NAME = "pipeline_status.json"


def build_pipeline_status(
    ledger: PipelineLedger,
    *,
    lane: str,
    wake_reason: str | None = None,
    extra: dict[str, Any] | None = None,
    pdf_disk_n: int | None = None,
    parsed_disk_n: int | None = None,
    live_n: int | None = None,
) -> dict[str, Any]:
    truth = pipeline_truth_snapshot(
        ledger,
        pdf_disk_n=pdf_disk_n,
        parsed_disk_n=parsed_disk_n,
        live_n=live_n,
    )
    status = {
        **truth,
        "lane": lane,
        "recorded_at": datetime.now(IST).isoformat(),
        "wake_reason": wake_reason,
    }
    if extra:
        status["extra"] = extra
    return status


def publish_pipeline_status(
    ledger: PipelineLedger,
    *,
    lane: str,
    wake_reason: str | None = None,
    extra: dict[str, Any] | None = None,
    pdf_disk_n: int | None = None,
    parsed_disk_n: int | None = None,
    live_n: int | None = None,
) -> dict[str, Any]:
    status = build_pipeline_status(
        ledger,
        lane=lane,
        wake_reason=wake_reason,
        extra=extra,
        pdf_disk_n=pdf_disk_n,
        parsed_disk_n=parsed_disk_n,
        live_n=live_n,
    )
    ok = push_pipeline_json(STATUS_NAME, status)
    if not ok:
        logger.warning("failed to push %s", STATUS_NAME)
    return status


def truth_for_telegram(status: dict[str, Any]) -> dict[str, Any]:
    """Compact fields for lane Telegram reports."""
    keys = (
        "parse_eligible",
        "publishable_future",
        "aged_out_parsed",
        "download_pending",
        "parse_done",
        "publishable_all",
        "pdfs_on_disk",
        "parsed_on_disk",
        "live_export_count",
        "min_closing_date",
    )
    return {k: status.get(k) for k in keys if status.get(k) is not None}
