from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.models import AuctionRecord

IST = ZoneInfo("Asia/Kolkata")


def tomorrow_min_closing_date(now: datetime | None = None) -> str:
    """Return tomorrow's date in IST as YYYY-MM-DD (future-only filter boundary)."""
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    else:
        current = current.astimezone(IST)
    return (current.date() + timedelta(days=1)).strftime("%Y-%m-%d")


def make_run_id(now: datetime | None = None) -> str:
    """Unique refresh run id: YYYYMMDD_HHMMSS_IST."""
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    else:
        current = current.astimezone(IST)
    return current.strftime("%Y%m%d_%H%M%S_IST")


def parse_min_closing_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD as 00:00:00 Asia/Kolkata."""
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=IST)


def normalize_closing(closing: datetime | None) -> datetime | None:
    if closing is None:
        return None
    if closing.tzinfo is None:
        return closing.replace(tzinfo=IST)
    return closing.astimezone(IST)


def passes_min_closing(record: AuctionRecord, min_closing: datetime | None) -> bool:
    if min_closing is None:
        return True
    closing = normalize_closing(record.closing)
    if closing is None:
        return False
    return closing >= min_closing


def apply_future_filter(
    records: list[AuctionRecord],
    min_closing: datetime | None,
) -> tuple[list[AuctionRecord], dict[str, int]]:
    if min_closing is None:
        return records, {
            "before_filter": len(records),
            "kept": len(records),
            "excluded_past_closing": 0,
            "excluded_missing_closing": 0,
        }

    kept: list[AuctionRecord] = []
    excluded_past = 0
    excluded_missing = 0

    for record in records:
        closing = normalize_closing(record.closing)
        if closing is None:
            excluded_missing += 1
            continue
        if closing < min_closing:
            excluded_past += 1
            continue
        kept.append(record)

    return kept, {
        "before_filter": len(records),
        "kept": len(kept),
        "excluded_past_closing": excluded_past,
        "excluded_missing_closing": excluded_missing,
    }
