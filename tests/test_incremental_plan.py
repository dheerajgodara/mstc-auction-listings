from __future__ import annotations

import json

from scraper.incremental import build_listing_snapshot, compare_exports
from scraper.incremental_plan import build_work_plan, mstc_ids_by_office_for_action, write_action_id_lists
from scraper.incremental_plan import ids_by_source_for_action, load_work_plan, write_work_plan


def _auction(
    auction_id: str = "582972",
    *,
    source: str = "mstc",
    closing: str = "2026-07-15T15:30:00+05:30",
    title: str = "Tower Parts and ACSR Conductor",
    lots: list[dict] | None = None,
    status: str = "complete",
    confidence: str = "high",
) -> dict:
    return {
        "id": auction_id if source == "mstc" else f"{source}:{auction_id}",
        "source": source,
        "source_auction_id": auction_id,
        "auction_number": f"MSTC/TEST/[{auction_id}]",
        "item_summary": title,
        "seller": "UP Power Transmission",
        "location": "Civil Line Ballia",
        "state": "Uttar Pradesh",
        "opening": "2026-07-10T11:00:00+05:30",
        "closing": closing,
        "detail_url": f"https://example.test/detail/{auction_id}",
        "pdf_url": f"pdfs/{auction_id}.pdf",
        "total_lots": len(lots if lots is not None else [{"lot_id": "1"}]),
        "lots": lots if lots is not None else [{"lot_id": "1", "item_title": "Tower Parts"}],
        "status": status,
        "parse_confidence": confidence,
        "missing_fields": [],
        "errors": [],
    }


def _export(*auctions: dict) -> dict:
    return {"generated_at": "2026-07-10T10:00:00+05:30", "count": len(auctions), "auctions": list(auctions)}


def _discovery_export(*auctions: dict, sources: list[str]) -> dict:
    data = _export(*auctions)
    data["stats"] = {"discovery_only": True, "source_stats": {source: {"complete": True} for source in sources}}
    return data


def test_listing_scope_ignores_lot_and_price_enrichment_changes():
    previous = _export(_auction(lots=[{"lot_id": "1", "item_title": "Old", "quantity": "1", "unit": "MT"}]))
    current = _export(_auction(lots=[], status="listing_only", confidence="low"))

    enriched = compare_exports(current, previous, scope="enriched")
    listing = compare_exports(current, previous, scope="listing")

    assert enriched.decisions[0].status == "changed"
    assert listing.decisions[0].status == "unchanged"
    assert build_listing_snapshot(current["auctions"][0], scope="listing").fields.get("lot_signature") is None


def test_mstc_listing_scope_ignores_detail_only_fields_missing_from_shallow_discovery():
    previous_record = _auction()
    previous_record["seller"] = "Detailed seller from HTML"
    previous_record["location"] = "Detailed yard from HTML"
    previous_record["item_summary"] = "Detailed PDF item summary"
    previous_record["document_urls"] = ["pdfs/582972.pdf"]
    discovery_record = dict(previous_record)
    discovery_record["seller"] = None
    discovery_record["location"] = None
    discovery_record["item_summary"] = None
    discovery_record["document_urls"] = []
    discovery_record["lots"] = []

    report = compare_exports(_export(discovery_record), _export(previous_record), scope="listing")

    assert report.decisions[0].status == "unchanged"


def test_work_plan_maps_decisions_to_actions():
    previous = _export(
        _auction("1"),
        _auction("2", closing="2026-07-15T15:30:00+05:30"),
        _auction("3"),
        _auction("4", lots=[], status="partial", confidence="low"),
    )
    discovery = _export(
        _auction("1"),
        _auction("2", closing="2026-07-16T15:30:00+05:30"),
        _auction("4", lots=[]),
        _auction("5"),
    )

    plan = build_work_plan(discovery, previous)
    by_key = {item.stable_key: item for item in plan.items}

    assert by_key["mstc:1"].action == "reuse_previous"
    assert by_key["mstc:2"].action == "deep_parse"
    assert by_key["mstc:4"].decision == "needs_repair"
    assert by_key["mstc:4"].action == "deep_parse"
    assert by_key["mstc:5"].decision == "new"
    assert by_key["mstc:5"].action == "deep_parse"
    assert by_key["mstc:3"].decision == "removed"
    assert by_key["mstc:3"].action == "mark_removed"
    assert plan.action_counts == {"reuse_previous": 1, "deep_parse": 3, "mark_removed": 1}


def test_write_action_id_lists(tmp_path):
    previous = _export(_auction("1"), _auction("2", source="gem_forward"))
    discovery = _export(_auction("1"), _auction("3", source="gem_forward"))
    plan = build_work_plan(discovery, previous)

    write_action_id_lists(tmp_path, plan)

    assert json.loads((tmp_path / "reuse_previous_mstc.json").read_text()) == ["1"]
    assert json.loads((tmp_path / "deep_parse_gem_forward.json").read_text()) == ["3"]
    assert json.loads((tmp_path / "mark_removed_gem_forward.json").read_text()) == ["2"]
    assert json.loads((tmp_path / "summary.json").read_text()) == {
        "reuse_previous": {"mstc": 1},
        "deep_parse": {"gem_forward": 1},
        "mark_removed": {"gem_forward": 1},
    }


def test_write_action_id_lists_removes_stale_files(tmp_path):
    stale = tmp_path / "deep_parse_mstc.json"
    stale.write_text('["old"]', encoding="utf-8")
    plan = build_work_plan(_discovery_export(_auction("1"), sources=["mstc"]), _export(_auction("1")))

    write_action_id_lists(tmp_path, plan)

    assert not stale.exists()
    assert json.loads((tmp_path / "reuse_previous_mstc.json").read_text()) == ["1"]


def test_work_plan_does_not_mark_undiscovered_sources_removed():
    previous = _export(_auction("1", source="mstc"), _auction("2", source="gem_forward"))
    discovery = _discovery_export(_auction("1", source="mstc"), sources=["mstc"])

    plan = build_work_plan(discovery, previous)

    assert plan.counts["removed"] == 0
    assert {item.source for item in plan.items} == {"mstc"}


def test_work_plan_suppresses_removals_for_partial_source_discovery():
    previous = _export(_auction("1", source="mstc"), _auction("2", source="mstc"))
    discovery = _export(_auction("1", source="mstc"))
    discovery["stats"] = {"discovery_only": True, "source_stats": {"mstc": {"complete": False}}}

    plan = build_work_plan(discovery, previous)

    assert plan.counts["removed"] == 0
    assert [item.stable_key for item in plan.items] == ["mstc:1"]


def test_work_plan_round_trip_and_action_id_grouping(tmp_path):
    previous = _export(_auction("1"), _auction("2", source="gem_forward"))
    discovery = _discovery_export(_auction("1"), _auction("3", source="gem_forward"), sources=["mstc", "gem_forward"])
    plan = build_work_plan(discovery, previous)
    path = tmp_path / "plan.json"

    write_work_plan(path, plan)
    loaded = load_work_plan(path)

    assert loaded.action_counts == plan.action_counts
    assert ids_by_source_for_action(loaded, "reuse_previous") == {"mstc": {"1"}}
    assert ids_by_source_for_action(loaded, "deep_parse") == {"gem_forward": {"3"}}


def test_work_plan_carries_mstc_office_metadata_for_runner():
    previous = _export(_auction("1"), _auction("2"))
    changed = _auction("2", closing="2026-07-16T15:30:00+05:30")
    changed["office"] = "HO"
    discovery = _discovery_export(_auction("1"), changed, sources=["mstc"])

    plan = build_work_plan(discovery, previous)

    assert mstc_ids_by_office_for_action(plan, "deep_parse") == {"HO": {"2"}}
