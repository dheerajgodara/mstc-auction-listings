from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.import_tracking import (
    apply_first_seen_tracking,
    build_daily_import_entry,
    finalize_export_payload,
    merge_import_history,
    stable_auction_key,
)

IST = ZoneInfo("Asia/Kolkata")


def _auction(aid: str, source: str = "mstc") -> dict:
    return {
        "id": aid,
        "source": source,
        "source_auction_id": aid,
        "auction_number": f"MSTC/{aid}",
        "region": "LKO",
        "office": "LKO",
        "lots": [],
    }


def test_stable_auction_key_uses_source_and_id():
    assert stable_auction_key(_auction("582972")) == "mstc:582972"
    assert stable_auction_key({"id": "x", "source": "eauction", "source_auction_id": "y"}) == "eauction:y"


def test_first_seen_preserved_from_previous_export():
    ran_at = datetime(2026, 7, 4, 11, 48, tzinfo=IST)
    prev_first = datetime(2026, 7, 1, 9, 0, tzinfo=IST)
    previous = {
        "generated_at": datetime(2026, 7, 3, 16, 5, tzinfo=IST).isoformat(),
        "auctions": [
            {**_auction("582972"), "first_seen_at": prev_first.isoformat(), "imported_at": prev_first.isoformat()},
        ],
    }
    current = [_auction("582972"), _auction("584985")]
    updated, new_count, removed = apply_first_seen_tracking(
        current,
        previous_export=previous,
        automation_ran_at=ran_at,
    )
    by_id = {a["id"]: a for a in updated}
    assert by_id["582972"]["first_seen_at"] == prev_first.isoformat()
    assert by_id["584985"]["first_seen_at"] == ran_at.isoformat()
    assert new_count == 1
    assert removed == 0


def test_backfill_first_seen_from_previous_generated_at():
    ran_at = datetime(2026, 7, 4, 12, 0, tzinfo=IST)
    prev_gen = datetime(2026, 7, 3, 16, 5, tzinfo=IST)
    previous = {
        "generated_at": prev_gen.isoformat(),
        "auctions": [_auction("582972"), _auction("584985")],
    }
    updated, new_count, _ = apply_first_seen_tracking(
        [_auction("582972"), _auction("584985")],
        previous_export=previous,
        automation_ran_at=ran_at,
    )
    assert new_count == 0
    for a in updated:
        assert a["first_seen_at"] == prev_gen.isoformat()
        assert a["last_seen_at"] == ran_at.isoformat()
        assert a["imported_at"] == a["first_seen_at"]


def test_last_seen_at_updates_each_run():
    first_run = datetime(2026, 7, 3, 10, 0, tzinfo=IST)
    second_run = datetime(2026, 7, 4, 10, 0, tzinfo=IST)
    previous = {
        "generated_at": first_run.isoformat(),
        "auctions": [
            {
                **_auction("582972"),
                "first_seen_at": first_run.isoformat(),
                "imported_at": first_run.isoformat(),
                "last_seen_at": first_run.isoformat(),
            }
        ],
    }
    updated, _, _ = apply_first_seen_tracking(
        [_auction("582972")],
        previous_export=previous,
        automation_ran_at=second_run,
    )
    assert updated[0]["first_seen_at"] == first_run.isoformat()
    assert updated[0]["last_seen_at"] == second_run.isoformat()


def test_merge_import_history_appends_and_trims():
    entry = build_daily_import_entry(
        automation_ran_at=datetime(2026, 7, 4, 11, 0, tzinfo=IST),
        run_id="run_a",
        count=100,
        total_lots=200,
        by_source={"mstc": 90, "eauction": 10},
        new_count=5,
        removed_count=1,
    )
    merged = merge_import_history([], entry)
    assert len(merged) == 1
    assert merged[0]["run_id"] == "run_a"

    entry2 = build_daily_import_entry(
        automation_ran_at=datetime(2026, 7, 4, 12, 0, tzinfo=IST),
        run_id="run_b",
        count=101,
        total_lots=201,
        by_source={"mstc": 91, "eauction": 10},
        new_count=1,
        removed_count=0,
    )
    merged2 = merge_import_history(merged, entry2)
    assert len(merged2) == 2
    # replace same run_id
    entry3 = {**entry2, "total_auctions": 102}
    merged3 = merge_import_history(merged2, entry3)
    assert len(merged3) == 2
    assert merged3[-1]["total_auctions"] == 102


def test_finalize_export_adds_run_metadata(tmp_path: Path):
    previous = {
        "generated_at": datetime(2026, 7, 3, 16, 5, tzinfo=IST).isoformat(),
        "count": 1,
        "auctions": [_auction("582972")],
        "stats": {},
    }
    candidate = {
        "generated_at": datetime(2026, 7, 4, 10, 0, tzinfo=IST).isoformat(),
        "count": 2,
        "auctions": [_auction("582972"), _auction("584985")],
        "stats": {"batch_manifest_summary": [{"source": "mstc", "status": "done"}]},
    }
    history_path = tmp_path / "import-history.json"
    out = finalize_export_payload(
        candidate,
        previous_export=previous,
        automation_ran_at=datetime(2026, 7, 4, 11, 48, tzinfo=IST),
        run_id="test_run",
        history_path=history_path,
    )
    assert out["automation_ran_at"].startswith("2026-07-04T11:48")
    assert out["export_generated_at"].startswith("2026-07-04T10:00")
    assert out["run_id"] == "test_run"
    assert out["sources"]["mstc"]["count"] == 2
    assert len(out["daily_import_summary"]) == 1
    assert history_path.is_file()
    by_id = {a["id"]: a for a in out["auctions"]}
    assert by_id["582972"]["first_seen_at"].startswith("2026-07-03")
    assert by_id["584985"]["first_seen_at"].startswith("2026-07-04T11:48")


def test_daily_import_entry_shape():
    entry = build_daily_import_entry(
        automation_ran_at=datetime(2026, 7, 4, 11, 48, tzinfo=IST),
        run_id="r1",
        count=1816,
        total_lots=5000,
        by_source={"mstc": 1681, "gem_forward": 74, "eauction": 61},
        new_count=3,
        removed_count=2,
    )
    assert entry["date"] == "2026-07-04"
    assert entry["mstc_auctions"] == 1681
    assert entry["new_auctions_first_seen"] == 3
