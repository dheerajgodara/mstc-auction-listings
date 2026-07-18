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


def test_materialize_keeps_previous_when_deep_parse_failed():
    previous = _export(_auction("1", title="Prior enriched"))
    previous["auctions"][0]["ai_clean_heading"] = "Keep me"
    discovery = _export(_auction("1", title="Shell", closing="2026-07-16T10:00:00+05:30"))
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, previous)
    failed = _auction("1", title="Broken parse", closing="2026-07-16T10:00:00+05:30")
    failed["status"] = "failed"
    failed["lots"] = []
    failed["errors"] = ["pdf: PDF missing for parse_only: /tmp/1.pdf"]

    out = materialize_incremental_export(
        work_plan=plan,
        previous_export=previous,
        parsed_export=_export(failed),
        discovery_export=discovery,
        allow_missing_deep_parse=True,
    )

    assert out["count"] == 1
    row = out["auctions"][0]
    assert row["ai_clean_heading"] == "Keep me"
    assert row["item_summary"] == "Prior enriched"
    assert "parse_repair_pending" in row["warnings"]
    assert out["stats"]["incremental_materialize"]["repair_kept_previous"] == 1


def test_materialize_reuse_previous_falls_back_to_discovery_for_new_listings():
    previous = _export(_auction("old", title="Old"))
    discovery = _export(
        _auction("old", title="Old"),
        _auction("new", title="Brand new listing"),
    )
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": True}}}
    plan = build_work_plan(discovery, previous)
    # Simulate parse-job rewrite: unselected deep_parse → reuse_previous (buggy path)
    # Materialize must still keep discovery-only rows via discovery fallback.
    adjusted = plan.model_copy(
        update={
            "items": [
                item.model_copy(update={"action": "reuse_previous"})
                if item.action == "deep_parse"
                else item
                for item in plan.items
            ]
        }
    )

    out = materialize_incremental_export(
        work_plan=adjusted,
        previous_export=previous,
        parsed_export=_export(),
        discovery_export=discovery,
        allow_missing_deep_parse=True,
    )

    by_id = {a["source_auction_id"]: a for a in out["auctions"]}
    assert out["count"] == 2
    assert by_id["new"]["status"] == "listing_only"
    assert "deep_enrichment_pending" in by_id["new"]["warnings"]


def test_materialize_carries_unplanned_previous_when_incomplete_discovery_omits_keys():
    previous = _export(
        _auction("kept_in_plan", title="In plan"),
        _auction("only_previous", title="Omitted from plan"),
    )
    discovery = _export(_auction("kept_in_plan", title="In plan"))
    discovery["stats"] = {
        "discovery_only": True,
        "source_stats": {"mstc": {"complete": False}},
    }
    plan = build_work_plan(discovery, previous)

    out = materialize_incremental_export(
        work_plan=plan,
        previous_export=previous,
        parsed_export=_export(),
        discovery_export=discovery,
        allow_missing_deep_parse=True,
    )

    by_id = {a["source_auction_id"]: a for a in out["auctions"]}
    assert "kept_in_plan" in by_id
    assert "only_previous" in by_id
    assert out["stats"]["incremental_materialize"]["carried_forward_unplanned_previous"] >= 1
