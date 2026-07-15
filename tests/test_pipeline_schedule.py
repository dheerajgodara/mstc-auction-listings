from __future__ import annotations

from scraper.schedule_guard import latest_slot_start
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def test_pipeline_download_uses_same_ist_slots_as_legacy():
    """Download workflow reuses schedule_guard TARGET_SLOTS_IST (00/06/12/18)."""
    now = datetime(2026, 7, 15, 16, 20, tzinfo=IST)
    assert latest_slot_start(now) == datetime(2026, 7, 15, 12, 0, tzinfo=IST)
