from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.safety_gates import SafetyGateConfig, run_safety_gates

IST = ZoneInfo("Asia/Kolkata")


def _record(rid: str) -> dict:
    return {
        "id": rid,
        "source": "mstc",
        "source_auction_id": rid,
        "auction_number": rid,
        "region": "JPR",
        "office": "JPR",
        "closing": "2026-07-10T10:00:00+05:30",
        "lots": [{"lot_id": "1", "item_title": "Item"}],
        "imported_at": datetime.now(IST).isoformat(),
        "first_seen_at": datetime.now(IST).isoformat(),
    }


def _write_candidate(path: Path, *, count: int = 1200, automation_ran_at: datetime | None = None) -> None:
    now = automation_ran_at or datetime.now(IST)
    auctions = [_record(f"m{i}") for i in range(count)]
    payload = {
        "generated_at": now.isoformat(),
        "automation_ran_at": now.isoformat(),
        "run_id": "test_run",
        "count": count,
        "auctions": auctions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_safety_gates_reject_missing_import_metadata(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    payload = {
        "generated_at": datetime.now(IST).isoformat(),
        "count": 2,
        "auctions": [
            {
                "id": "1",
                "auction_number": "1",
                "region": "JPR",
                "office": "JPR",
                "source": "mstc",
                "lots": [],
            }
        ],
    }
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    prod = tmp_path / "prod.json"
    _write_candidate(prod, count=1200)

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=1,
            min_closing_date="2026-01-01",
            production_json=prod,
        ),
    )
    assert not result.passed
    assert any("automation_ran_at" in e for e in result.errors)
    assert any("imported_at" in e for e in result.errors)


def test_safety_gates_warn_stale_automation(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    stale = datetime.now(IST) - timedelta(hours=50)
    _write_candidate(candidate, count=1200, automation_ran_at=stale)
    prod = tmp_path / "prod.json"
    _write_candidate(prod, count=1200)

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=1,
            min_closing_date="2026-01-01",
            production_json=prod,
        ),
    )
    assert any("older than 48" in w for w in result.warnings)


def test_safety_gates_block_very_stale_automation(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    stale = datetime.now(IST) - timedelta(days=8)
    _write_candidate(candidate, count=1200, automation_ran_at=stale)
    prod = tmp_path / "prod.json"
    _write_candidate(prod, count=1200)

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=1,
            min_closing_date="2026-01-01",
            production_json=prod,
        ),
    )
    assert not result.passed
    assert any("older than 7 days" in e for e in result.errors)
