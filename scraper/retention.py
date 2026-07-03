from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.config import MIN_OPENING_YEAR, RETENTION_DAYS
from scraper.models import ListingApiAuction

IST = ZoneInfo("Asia/Kolkata")


def should_keep_auction(
    auction: ListingApiAuction,
    *,
    today: datetime | None = None,
    retention_days: int = RETENTION_DAYS,
    min_opening_year: int = MIN_OPENING_YEAR,
) -> bool:
    """
    Keep auction if closing is within retention window and opening year is recent enough.

    closing_date >= today - retention_days
    """
    from scraper.mstc_api import parse_mstc_datetime

    now = today or datetime.now(IST)
    closing = parse_mstc_datetime(auction.Closing)
    opening = parse_mstc_datetime(auction.opening)

    if closing is None:
        return False

    cutoff = now - timedelta(days=retention_days)
    if closing < cutoff:
        return False

    if opening and opening.year < min_opening_year:
        return False

    return True
