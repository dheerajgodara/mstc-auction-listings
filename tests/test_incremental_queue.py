from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.incremental_plan import build_work_plan
from scraper.incremental_queue import apply_queue_limit, finalize_queue_after_run
from scraper.incremental_materialize import materialize_incremental_export

IST = ZoneInfo("Asia/Kolkata")


def _auction(
    auction_id: str,
    *,
    title: str = "Auction",
    source: str = "mstc",
    closing: str = "2026-07-15T10:00:00+05:30",
    status: str = "complete",
) -> dict:
    return {
        "id": auction_id if source == "mstc" else f"{source}:{auction_id}",
        "source": source,
        "source_auction_id": auction_id,
        "auction_number": auction_id,
        "region": "HO",
        "office": "HO",
        "closing": closing,
        "item_summary": title,
        "lots": [{"lot_id": "1", "item_title": title}] if status != "listing_only" else [],
        "status": status,
        "parse_confidence": "high" if status == "complete" else "minimal",
        "missing_fields": [] if status == "complete" else ["lots"],
        "errors": [],
    }


def _export(*auctions: dict) -> dict:
    return {"generated_at": "2026-07-10T10:00:00+05:30", "count": len(auctions), "auctions": list(auctions)}


def test_queue_limits_deep_parse_to_cap_and_keeps_pending(tmp_path: Path):
    now = datetime(2026, 7, 10, 10, tzinfo=IST)
    discovery = _export(*[_auction(str(i), title=f"New {i}") for i in range(10)])
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, _export())

    limited, queue = apply_queue_limit(
        plan,
        queue_path=tmp_path / "queue.json",
        max_deep_scrape_per_run=3,
        previous_export=_export(),
        now=now,
    )

    assert plan.action_counts["deep_parse"] == 10
    assert limited.action_counts["deep_parse"] == 3
    assert limited.action_counts["reuse_discovery"] == 7
    assert queue.selected_count == 3
    assert queue.pending_after_selection == 10
    assert queue.estimated_runs_to_clear == 3


def test_queue_next_run_continues_from_pending_after_success(tmp_path: Path):
    now = datetime(2026, 7, 10, 10, tzinfo=IST)
    discovery = _export(*[_auction(str(i), title=f"New {i}") for i in range(5)])
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, _export())
    queue_path = tmp_path / "queue.json"

    limited, queue = apply_queue_limit(
        plan,
        queue_path=queue_path,
        max_deep_scrape_per_run=2,
        previous_export=_export(),
        now=now,
    )
    selected = set(queue.selected_keys)
    parsed = _export(*[_auction(key.split(":", 1)[1], title="Parsed") for key in selected])
    finalize_queue_after_run(
        queue_path=queue_path,
        selected_keys=selected,
        parsed_export=parsed,
        max_deep_scrape_per_run=2,
        previous_export=_export(),
        now=now + timedelta(minutes=10),
    )

    limited2, queue2 = apply_queue_limit(
        plan,
        queue_path=queue_path,
        max_deep_scrape_per_run=2,
        previous_export=_export(),
        now=now + timedelta(hours=3),
    )
    assert not selected & set(queue2.selected_keys)
    assert limited2.action_counts["deep_parse"] == 2


def test_failed_item_retries_with_delay(tmp_path: Path):
    now = datetime(2026, 7, 10, 10, tzinfo=IST)
    discovery = _export(_auction("1"))
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, _export())
    queue_path = tmp_path / "queue.json"

    _, queue = apply_queue_limit(plan, queue_path=queue_path, max_deep_scrape_per_run=1, previous_export=_export(), now=now)
    finalize_queue_after_run(
        queue_path=queue_path,
        selected_keys=set(queue.selected_keys),
        parsed_export=_export(),
        max_deep_scrape_per_run=1,
        previous_export=_export(),
        now=now + timedelta(minutes=1),
    )
    _, retry_now = apply_queue_limit(
        plan,
        queue_path=queue_path,
        max_deep_scrape_per_run=1,
        previous_export=_export(),
        now=now + timedelta(hours=3),
    )
    assert retry_now.selected_count == 1

    finalize_queue_after_run(
        queue_path=queue_path,
        selected_keys=set(retry_now.selected_keys),
        parsed_export=_export(),
        max_deep_scrape_per_run=1,
        previous_export=_export(),
        now=now + timedelta(hours=3, minutes=1),
    )
    _, delayed = apply_queue_limit(
        plan,
        queue_path=queue_path,
        max_deep_scrape_per_run=1,
        previous_export=_export(),
        now=now + timedelta(hours=4),
    )
    assert delayed.selected_count == 0


def test_materialize_keeps_shallow_pending_discovery_records(tmp_path: Path):
    previous = _export(_auction("old"))
    discovery = _export(_auction("old"), _auction("new", title="Shallow new"))
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, previous)
    limited, _ = apply_queue_limit(
        plan,
        queue_path=tmp_path / "queue.json",
        max_deep_scrape_per_run=0 + 1,
        previous_export=previous,
        now=datetime(2026, 7, 10, 10, tzinfo=IST),
    )
    # Force all deep work into pending shallow for this assertion.
    limited = limited.model_copy(
        update={"items": [item.model_copy(update={"action": "reuse_discovery"}) if item.action == "deep_parse" else item for item in limited.items]}
    )
    out = materialize_incremental_export(
        work_plan=limited,
        previous_export=previous,
        parsed_export=_export(),
        discovery_export=discovery,
        allow_missing_deep_parse=True,
    )
    by_id = {a["source_auction_id"]: a for a in out["auctions"]}
    assert by_id["new"]["status"] == "listing_only"
    assert "deep_enrichment_pending" in by_id["new"]["warnings"]


def test_materialize_pending_changed_record_prefers_fresh_discovery_over_previous(tmp_path: Path):
    previous = _export(
        _auction(
            "577846",
            title="Old enriched",
            closing="2026-07-04T14:00:00+05:30",
        )
    )
    discovery = _export(
        _auction(
            "577846",
            title="Fresh shell",
            closing="2026-07-15T14:00:00+05:30",
            status="listing_only",
        )
    )
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, previous)
    limited = plan.model_copy(
        update={
            "items": [
                item.model_copy(update={"action": "reuse_discovery"})
                if item.action == "deep_parse"
                else item
                for item in plan.items
            ]
        }
    )

    out = materialize_incremental_export(
        work_plan=limited,
        previous_export=previous,
        parsed_export=_export(),
        discovery_export=discovery,
        allow_missing_deep_parse=True,
    )

    assert out["count"] == 1
    record = out["auctions"][0]
    assert record["closing"] == "2026-07-15T14:00:00+05:30"
    assert record["item_summary"] == "Fresh shell"
    assert record["status"] == "listing_only"
    assert "deep_enrichment_pending" in record["warnings"]
