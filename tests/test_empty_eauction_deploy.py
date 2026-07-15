"""Empty eAuction / source-fallback must not hard-stop the pipeline."""

from __future__ import annotations

from scraper.export_hygiene import strip_aged_out_auctions
from scraper.source_fallback import apply_missing_source_fallback, source_counts


def _row(aid: str, *, source: str, closing: str) -> dict:
    return {
        "id": aid,
        "source": source,
        "source_auction_id": aid,
        "auction_number": aid,
        "closing": closing,
        "lots": [{"lot_id": "1"}],
        "status": "complete",
    }


def _export(rows: list[dict]) -> dict:
    return {
        "generated_at": "2026-07-16T12:00:00+05:30",
        "count": len(rows),
        "auctions": rows,
        "stats": {"by_source": source_counts({"auctions": rows})},
    }


def test_fallback_then_strip_keeps_future_eauction_only():
    previous = _export(
        [
            _row("ea-old", source="eauction", closing="2026-07-16T10:00:00+05:30"),
            _row("ea-ok", source="eauction", closing="2026-07-20T10:00:00+05:30"),
            _row("m1", source="mstc", closing="2026-07-20T10:00:00+05:30"),
        ]
    )
    # Candidate lost all eAuction (discovery empty / aged-out strip).
    candidate = _export(
        [_row("m1", source="mstc", closing="2026-07-20T10:00:00+05:30")]
    )
    filled, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-17",
        fallback_sources=["eauction", "gem_forward"],
    )
    assert report.get("applied") is True
    assert source_counts(filled).get("eauction", 0) >= 1

    cleaned = strip_aged_out_auctions(filled, min_closing_date="2026-07-17")
    ids = {a["id"] for a in cleaned.export["auctions"]}
    assert "ea-old" not in ids
    assert "ea-ok" in ids
    assert "m1" in ids
    # No residual closes-before rows.
    for a in cleaned.export["auctions"]:
        assert a["closing"] >= "2026-07-17"


def test_fallback_noop_when_previous_also_empty_eauction():
    previous = _export(
        [_row("m1", source="mstc", closing="2026-07-20T10:00:00+05:30")]
    )
    candidate = _export(
        [
            _row("m1", source="mstc", closing="2026-07-20T10:00:00+05:30"),
            _row("g1", source="gem_forward", closing="2026-07-20T10:00:00+05:30"),
        ]
    )
    filled, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-17",
        fallback_sources=["eauction", "gem_forward"],
    )
    assert source_counts(filled).get("eauction", 0) == 0
    # Missing eauction alone is not a hard pipeline failure — export still valid.
    assert filled["count"] >= 2
