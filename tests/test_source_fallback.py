from __future__ import annotations

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
