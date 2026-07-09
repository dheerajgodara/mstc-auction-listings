from __future__ import annotations

import pytest

from scraper.incremental_materialize import materialize_incremental_export
from scraper.incremental_plan import build_work_plan


def _auction(
    auction_id: str,
    *,
    source: str = "mstc",
    title: str = "Auction",
    closing: str = "2026-07-15T10:00:00+05:30",
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
        "lots": [{"lot_id": "1", "item_title": title}],
        "status": "complete",
        "parse_confidence": "high",
        "missing_fields": [],
        "errors": [],
    }


def _export(*auctions: dict) -> dict:
    return {"generated_at": "2026-07-10T10:00:00+05:30", "count": len(auctions), "auctions": list(auctions)}


def test_materialize_combines_reused_previous_and_deep_parsed_records():
    previous_reused = _auction("1", title="Old enriched")
    previous_reused["ai_clean_heading"] = "Preserved AI"
    previous_changed = _auction("2", title="Old title", closing="2026-07-15T10:00:00+05:30")
    previous_removed = _auction("3", title="Removed")

    discovery_reused = _auction("1", title="Discovery shell")
    discovery_changed = _auction("2", title="New title", closing="2026-07-16T10:00:00+05:30")
    discovery_new = _auction("4", title="New listing")
    discovery = _export(discovery_reused, discovery_changed, discovery_new)
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}

    plan = build_work_plan(discovery, _export(previous_reused, previous_changed, previous_removed))
    parsed_changed = _auction("2", title="Deep parsed changed", closing="2026-07-16T10:00:00+05:30")
    parsed_new = _auction("4", title="Deep parsed new")

    output = materialize_incremental_export(
        work_plan=plan,
        previous_export=_export(previous_reused, previous_changed, previous_removed),
        parsed_export=_export(parsed_changed, parsed_new),
    )

    by_id = {a["source_auction_id"]: a for a in output["auctions"]}
    assert output["count"] == 3
    assert by_id["1"]["ai_clean_heading"] == "Preserved AI"
    assert by_id["2"]["item_summary"] == "Deep parsed changed"
    assert by_id["4"]["item_summary"] == "Deep parsed new"
    assert "3" not in by_id
    assert output["stats"]["incremental_materialize"]["reused_previous_records"] == 1
    assert output["stats"]["incremental_materialize"]["deep_parsed_records"] == 2
    assert output["stats"]["incremental_materialize"]["removed_records"] == 1


def test_materialize_fails_when_deep_parse_record_is_missing():
    previous = _export(_auction("1", title="Old", closing="2026-07-15T10:00:00+05:30"))
    discovery = _export(_auction("1", title="Changed", closing="2026-07-16T10:00:00+05:30"))
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, previous)

    with pytest.raises(ValueError, match="Missing parsed records"):
        materialize_incremental_export(
            work_plan=plan,
            previous_export=previous,
            parsed_export=_export(),
        )
