from __future__ import annotations

from unittest.mock import patch

from scraper.discovery import discover_mstc
from scraper.incremental_plan import build_work_plan
from scraper.source_fallback import apply_missing_source_fallback, source_counts


def _auction(aid: str, source: str, closing: str = "2026-07-12T10:00:00+05:30") -> dict:
    return {
        "id": aid,
        "source": source,
        "source_auction_id": aid,
        "auction_number": aid,
        "region": "JPR",
        "office": "JPR",
        "closing": closing,
        "lots": [{"lot_id": "1", "item_title": "Item"}],
    }


def test_missing_source_fallback_carries_future_records_only():
    candidate = {
        "generated_at": "2026-07-10T06:00:00+05:30",
        "count": 2,
        "auctions": [_auction("m1", "mstc"), _auction("g1", "gem_forward")],
        "stats": {},
    }
    previous = {
        "generated_at": "2026-07-09T06:00:00+05:30",
        "count": 4,
        "auctions": [
            _auction("m-old", "mstc"),
            _auction("e-future", "eauction", "2026-07-12T10:00:00+05:30"),
            _auction("e-past", "eauction", "2026-07-10T06:00:00+05:30"),
        ],
    }

    out, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-11",
        fallback_sources=["eauction"],
    )

    assert report["applied"] is True
    assert report["sources"]["eauction"]["carried_forward"] == 1
    assert out["count"] == 3
    assert source_counts(out)["eauction"] == 1
    carried = next(a for a in out["auctions"] if a["id"] == "e-future")
    assert "carried forward" in carried["warnings"][0]
    assert all(a["id"] != "e-past" for a in out["auctions"])


def test_missing_source_fallback_does_not_override_fresh_source():
    candidate = {
        "generated_at": "2026-07-10T06:00:00+05:30",
        "count": 2,
        "auctions": [_auction("m1", "mstc"), _auction("e-new", "eauction")],
        "stats": {},
    }
    previous = {"auctions": [_auction("e-old", "eauction")]}

    out, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-11",
        fallback_sources=["eauction"],
    )

    assert report["applied"] is False
    assert out["count"] == 2
    assert all(a["id"] != "e-old" for a in out["auctions"])


def test_missing_source_fallback_carries_mstc_when_discovery_zero():
    candidate = {
        "generated_at": "2026-07-10T06:00:00+05:30",
        "count": 1,
        "auctions": [_auction("e1", "eauction")],
        "stats": {
            "by_source": {"eauction": 1},
            "source_stats": {
                "mstc": {"source": "mstc", "complete": False, "before_filter": 0},
                "eauction": {"source": "eauction", "complete": True},
            },
        },
    }
    previous = {
        "generated_at": "2026-07-09T06:00:00+05:30",
        "count": 3,
        "auctions": [
            _auction("m-future", "mstc", "2026-07-12T10:00:00+05:30"),
            _auction("m-past", "mstc", "2026-07-10T06:00:00+05:30"),
        ],
    }

    out, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-11",
        fallback_sources=["mstc", "eauction"],
    )

    assert report["applied"] is True
    assert report["sources"]["mstc"]["carried_forward"] == 1
    assert report["sources"]["mstc"]["reason"] == "source discovery incomplete"
    assert source_counts(out)["mstc"] == 1
    assert any(a["id"] == "m-future" for a in out["auctions"])
    assert all(a["id"] != "m-past" for a in out["auctions"])


def test_missing_source_fallback_carries_missing_records_for_partial_incomplete_source():
    candidate = {
        "generated_at": "2026-07-10T06:00:00+05:30",
        "count": 1,
        "auctions": [_auction("m-new", "mstc")],
        "stats": {
            "by_source": {"mstc": 1},
            "source_stats": {
                "mstc": {"source": "mstc", "complete": False, "failed_offices": ["JPR"]},
            },
        },
    }
    previous = {
        "generated_at": "2026-07-09T06:00:00+05:30",
        "count": 2,
        "auctions": [_auction("m-old", "mstc")],
    }

    out, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-11",
        fallback_sources=["mstc"],
    )

    assert report["applied"] is True
    assert source_counts(out)["mstc"] == 2
    assert {a["id"] for a in out["auctions"]} == {"m-new", "m-old"}


def test_mstc_discovery_is_incomplete_when_no_offices_fetch():
    with patch("scraper.discovery.fetch_all_listing_api", return_value=[]):
        records, stats = discover_mstc(office_codes=["HO", "JPR"], min_closing_date="2026-07-11")

    assert records == []
    assert stats["complete"] is False
    assert stats["requested_offices"] == ["HO", "JPR"]
    assert stats["fetched_offices"] == []
    assert stats["failed_offices"] == ["HO", "JPR"]


def test_carried_forward_incomplete_source_is_reused_not_deep_scraped():
    candidate = {
        "generated_at": "2026-07-10T06:00:00+05:30",
        "count": 0,
        "auctions": [],
        "stats": {
            "by_source": {},
            "source_stats": {"mstc": {"source": "mstc", "complete": False}},
        },
    }
    previous = {
        "generated_at": "2026-07-09T06:00:00+05:30",
        "count": 1,
        "auctions": [
            {
                **_auction("m-repair", "mstc"),
                "status": "partial",
                "parse_confidence": "low",
                "errors": ["old parse issue"],
            }
        ],
    }
    discovery, _report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-11",
        fallback_sources=["mstc"],
    )

    plan = build_work_plan(discovery, previous)

    assert plan.action_counts == {"reuse_previous": 1}
    assert plan.by_source["mstc"]["reuse_previous"] == 1
    assert plan.by_source["mstc"].get("deep_parse", 0) == 0
    assert plan.items[0].decision == "unchanged"
    assert "source_fallback_carried_forward" in plan.items[0].reasons
