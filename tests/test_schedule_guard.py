from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.schedule_guard import latest_slot_start, should_skip_for_existing_run

IST = ZoneInfo("Asia/Kolkata")


def test_latest_slot_start_uses_ist_slots():
    now = datetime(2026, 7, 10, 18, 44, tzinfo=IST)
    slot = latest_slot_start(now)
    assert slot == datetime(2026, 7, 10, 18, 30, tzinfo=IST)


def test_latest_slot_start_rolls_to_previous_day():
    now = datetime(2026, 7, 10, 0, 12, tzinfo=IST)
    slot = latest_slot_start(now)
    assert slot == datetime(2026, 7, 9, 21, 30, tzinfo=IST)


def test_schedule_guard_skips_if_slot_already_succeeded():
    slot = datetime(2026, 7, 10, 18, 30, tzinfo=IST)
    runs = [
        {
            "id": 111,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-07-10T13:01:00Z",
        }
    ]
    skip, reason = should_skip_for_existing_run(runs, current_run_id="222", slot_start=slot)
    assert skip is True
    assert "completed successfully" in reason


def test_schedule_guard_proceeds_if_prior_attempt_failed():
    slot = datetime(2026, 7, 10, 18, 30, tzinfo=IST)
    runs = [
        {
            "id": 111,
            "status": "completed",
            "conclusion": "failure",
            "created_at": "2026-07-10T13:01:00Z",
        }
    ]
    skip, reason = should_skip_for_existing_run(runs, current_run_id="222", slot_start=slot)
    assert skip is False
    assert "no successful" in reason


def test_schedule_guard_skips_if_slot_is_running():
    slot = datetime(2026, 7, 10, 18, 30, tzinfo=IST)
    runs = [
        {
            "id": 111,
            "status": "in_progress",
            "conclusion": None,
            "created_at": "2026-07-10T13:00:30Z",
        }
    ]
    skip, reason = should_skip_for_existing_run(runs, current_run_id="222", slot_start=slot)
    assert skip is True
    assert "already in_progress" in reason
