from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.schedule_guard import latest_slot_start, should_skip_for_existing_run
from scraper.ai_schedule_guard import latest_ai_slot_start

IST = ZoneInfo("Asia/Kolkata")


def test_latest_slot_start_uses_ist_slots():
    now = datetime(2026, 7, 10, 18, 44, tzinfo=IST)
    slot = latest_slot_start(now)
    assert slot == datetime(2026, 7, 10, 18, 0, tzinfo=IST)


def test_latest_slot_start_midday_uses_0600():
    now = datetime(2026, 7, 10, 10, 12, tzinfo=IST)
    slot = latest_slot_start(now)
    assert slot == datetime(2026, 7, 10, 6, 0, tzinfo=IST)


def test_latest_slot_start_rolls_to_previous_day():
    now = datetime(2026, 7, 10, 0, 12, tzinfo=IST)
    slot = latest_slot_start(now)
    assert slot == datetime(2026, 7, 10, 0, 0, tzinfo=IST)


def test_latest_slot_start_before_midnight_uses_previous_1800():
    now = datetime(2026, 7, 10, 2, 0, tzinfo=IST)
    slot = latest_slot_start(now)
    assert slot == datetime(2026, 7, 10, 0, 0, tzinfo=IST)


def test_latest_ai_slot_start_uses_offset_slots():
    now = datetime(2026, 7, 10, 8, 18, tzinfo=IST)
    slot = latest_ai_slot_start(now)
    assert slot == datetime(2026, 7, 10, 7, 5, tzinfo=IST)


def test_latest_ai_slot_start_rolls_to_previous_day():
    now = datetime(2026, 7, 10, 0, 45, tzinfo=IST)
    slot = latest_ai_slot_start(now)
    assert slot == datetime(2026, 7, 9, 19, 5, tzinfo=IST)


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


def test_schedule_guard_skips_older_running_run_to_prevent_backlog():
    slot = datetime(2026, 7, 10, 18, 40, tzinfo=IST)
    runs = [
        {
            "id": 111,
            "status": "in_progress",
            "conclusion": None,
            "created_at": "2026-07-10T12:30:00Z",
        }
    ]
    skip, reason = should_skip_for_existing_run(runs, current_run_id="222", slot_start=slot)
    assert skip is True
    assert "already in_progress" in reason
