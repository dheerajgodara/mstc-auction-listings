from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.models import AuctionRecord

IST = ZoneInfo("Asia/Kolkata")


def tomorrow_min_closing_date(now: datetime | None = None) -> str:
    """Return tomorrow's date in IST as YYYY-MM-DD (legacy date-only boundary)."""
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


def _as_ist(now: datetime | None = None) -> datetime:
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        return current.replace(tzinfo=IST)
    return current.astimezone(IST)


def min_closing_datetime(
    *,
    now: datetime | None = None,
    hours_ahead: int | None = None,
) -> datetime:
    """Hour-aware min runway: now (IST) + hours_ahead."""
    from scraper.config import MIN_CLOSING_HOURS_AHEAD

    hours = MIN_CLOSING_HOURS_AHEAD if hours_ahead is None else int(hours_ahead)
    return _as_ist(now) + timedelta(hours=hours)


def normalize_closing(closing: datetime | None) -> datetime | None:
    if closing is None:
        return None
    if closing.tzinfo is None:
        return closing.replace(tzinfo=IST)
    return closing.astimezone(IST)


def parse_min_closing_boundary(value: str) -> datetime:
    """Parse YYYY-MM-DD (midnight IST) or ISO datetime into an IST-aware boundary."""
    text = (value or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return parse_min_closing_date(text)
    parsed = normalize_closing(datetime.fromisoformat(text.replace("Z", "+00:00")))
    if parsed is None:
        raise ValueError(f"invalid min closing boundary: {value!r}")
    return parsed


def resolve_min_closing(
    force_min_closing_date: str | None = None,
    *,
    now: datetime | None = None,
    hours_ahead: int | None = None,
) -> datetime:
    """Production boundary: force YYYY-MM-DD/ISO override, else now + MIN_CLOSING_HOURS_AHEAD."""
    force = (force_min_closing_date or "").strip()
    if force:
        return parse_min_closing_boundary(force)
    return min_closing_datetime(now=now, hours_ahead=hours_ahead)


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
