from __future__ import annotations

from scraper.incremental import (
    build_listing_snapshot,
    compare_exports,
    merge_reusing_unchanged_records,
    repair_reasons_for,
    stable_listing_key,
)


def _auction(
    auction_id: str = "582972",
    *,
    source: str = "mstc",
    source_auction_id: str | None = None,
    closing: str = "2026-07-15T15:30:00+05:30",
    title: str = "Tower Parts and ACSR Conductor",
    lots: list[dict] | None = None,
    status: str = "complete",
    confidence: str = "high",
) -> dict:
    return {
        "id": auction_id if source == "mstc" else f"{source}:{auction_id}",
        "source": source,
        "source_auction_id": source_auction_id or auction_id,
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
        "lots": lots
        if lots is not None
        else [
            {
                "lot_id": "1",
                "item_title": "Tower Parts",
                "quantity": "430353",
                "unit": "KG",
                "start_price_inr": 1,
                "documents": [{"filename": "Annex.pdf"}],
            }
        ],
        "min_start_price": 1,
        "max_start_price": 1,
        "price_parse_status": "numeric",
        "emd_parse_status": "item_wise",
        "status": status,
        "parse_confidence": confidence,
        "missing_fields": [],
        "errors": [],
    }


def _export(*auctions: dict) -> dict:
    return {"generated_at": "2026-07-10T10:00:00+05:30", "count": len(auctions), "auctions": list(auctions)}


def test_stable_listing_key_does_not_double_prefix_source_id():
    assert stable_listing_key({"id": "gem_forward:36121", "source": "gem_forward"}) == "gem_forward:36121"
    assert stable_listing_key({"id": "x", "source": "eauction", "source_auction_id": "2026_MH_34847"}) == "eauction:2026_MH_34847"


def test_snapshot_hash_is_stable_for_equivalent_records():
    left = build_listing_snapshot(_auction(title="Tower   Parts\nand ACSR Conductor"))
    right = build_listing_snapshot(_auction(title="tower parts and acsr conductor"))
    assert left.stable_key == "mstc:582972"
    assert left.listing_hash == right.listing_hash


def test_compare_marks_absent_previous_as_new():
    report = compare_exports(_export(_auction()), None)
    assert report.counts["new"] == 1
    assert report.decisions[0].status == "new"


def test_compare_marks_same_record_as_unchanged():
    previous = _export(_auction())
    current = _export(_auction())
    report = compare_exports(current, previous)
    assert report.counts["unchanged"] == 1
    assert report.decisions[0].status == "unchanged"


def test_compare_marks_listing_field_change():
    previous = _export(_auction(closing="2026-07-15T15:30:00+05:30"))
    current = _export(_auction(closing="2026-07-16T15:30:00+05:30"))
    report = compare_exports(current, previous)
    assert report.counts["changed"] == 1
    assert report.decisions[0].status == "changed"
    assert "changed_closing" in report.decisions[0].reasons


def test_compare_marks_previous_broken_record_as_needs_repair_even_if_listing_unchanged():
    previous = _export(_auction(lots=[], status="partial", confidence="low"))
    current = _export(_auction(lots=[]))
    report = compare_exports(current, previous)
    assert report.counts["needs_repair"] == 1
    assert report.decisions[0].status == "needs_repair"
    assert "missing_lots" in report.decisions[0].reasons
    assert "status_partial" in report.decisions[0].reasons


def test_compare_marks_missing_current_as_removed():
    previous = _export(_auction("582972"), _auction("584985", title="Aluminium Scrap"))
    current = _export(_auction("582972"))
    report = compare_exports(current, previous)
    removed = [d for d in report.decisions if d.status == "removed"]
    assert len(removed) == 1
    assert removed[0].stable_key == "mstc:584985"


def test_repair_reasons_flag_failed_records_with_errors_and_missing_price():
    record = _auction(status="failed")
    record["errors"] = ["pdf_parse_failed"]
    record["missing_fields"] = ["start_price"]
    record["price_parse_status"] = "missing"
    reasons = repair_reasons_for(record)
    assert reasons == ["has_errors", "missing_price", "status_failed"]


def test_merge_reuses_previous_enriched_record_when_unchanged():
    previous_record = _auction()
    previous_record["ai_clean_heading"] = "AI enriched tower scrap"
    previous_record["lots"][0]["preview_images"] = ["thumbs/582972/1/a.webp"]
    current_record = _auction()
    current_record["ai_clean_heading"] = None
    current_record["lots"][0]["preview_images"] = []

    merged, report = merge_reusing_unchanged_records(_export(current_record), _export(previous_record))

    assert report.counts["unchanged"] == 1
    assert merged["count"] == 1
    assert merged["auctions"][0]["ai_clean_heading"] == "AI enriched tower scrap"
    assert merged["auctions"][0]["lots"][0]["preview_images"] == ["thumbs/582972/1/a.webp"]
    assert merged["stats"]["incremental"]["reused_unchanged_records"] == 1


def test_merge_keeps_current_record_when_changed():
    previous_record = _auction(closing="2026-07-15T15:30:00+05:30")
    previous_record["ai_clean_heading"] = "Old enrichment"
    current_record = _auction(closing="2026-07-16T15:30:00+05:30")
    current_record["ai_clean_heading"] = "Fresh candidate"

    merged, report = merge_reusing_unchanged_records(_export(current_record), _export(previous_record))

    assert report.counts["changed"] == 1
    assert merged["auctions"][0]["ai_clean_heading"] == "Fresh candidate"
    assert merged["stats"]["incremental"]["reused_unchanged_records"] == 0


def test_merge_keeps_current_record_when_previous_needs_repair():
    previous_record = _auction(lots=[], status="partial", confidence="low")
    previous_record["ai_clean_heading"] = "Broken previous"
    current_record = _auction(lots=[], status="complete", confidence="high")
    current_record["ai_clean_heading"] = "Current repair attempt"

    merged, report = merge_reusing_unchanged_records(_export(current_record), _export(previous_record))

    assert report.counts["needs_repair"] == 1
    assert merged["auctions"][0]["ai_clean_heading"] == "Current repair attempt"
    assert merged["stats"]["incremental"]["needs_repair_records"] == 1
