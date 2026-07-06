from __future__ import annotations

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.display_enrichment import apply_display_enrichment, normalize_location as py_normalize
from scraper.models import AuctionRecord, LotRecord

IST = ZoneInfo("Asia/Kolkata")


def _lot(
    lot_id: str,
    title: str,
    *,
    quantity: str | None = None,
    unit: str | None = None,
) -> LotRecord:
    return LotRecord(
        lot_id=lot_id,
        item_title=title,
        quantity=quantity,
        unit=unit,
    )


def test_format_mt_does_not_strip_trailing_zero_from_hundreds():
    from scraper.display_enrichment import _format_mt

    assert _format_mt(430.353) == "430"
    assert _format_mt(100.0) == "100"
    assert _format_mt(1000.5) == "1,000"


def test_enrich_582972_transmission_tower_title():
    record = AuctionRecord(
        id="582972",
        auction_number="MSTC/582972",
        region="LKO",
        office="LKO",
        state="Uttar Pradesh",
        location="CIVIL LINE BALLIA",
        item_summary="Tower Parts; Earthwire 7/3.15mm; ACSR Dog CONDUCTOR",
        lots=[
            _lot("1", "Tower Parts", quantity="430353", unit="KG"),
            _lot("2", "Earthwire 7/3.15mm", quantity="28800", unit="KG"),
            _lot("3", "ACSR Dog CONDUCTOR", quantity="1", unit="LOT"),
        ],
    )
    enriched = apply_display_enrichment(record)
    assert "Transmission" in enriched.display_title
    assert "459" in enriched.display_title or "459.15" in enriched.display_title
    assert enriched.display_location_city == "Ballia"
    assert enriched.display_location_state == "Uttar Pradesh"
    assert enriched.display_location_confidence == "high"
    assert enriched.display_material_category == "transmission_scrap"
    assert enriched.display_quantity_summary
    assert "430 MT Tower Parts" in enriched.display_quantity_summary
    assert "43 MT Tower Parts" not in enriched.display_quantity_summary
    assert "Tower Parts" in enriched.display_key_lots


def test_enrich_584985_aluminium_scrap():
    record = AuctionRecord(
        id="584985",
        auction_number="MSTC/584985",
        region="BLR",
        office="BLR",
        state="Karnataka",
        location="Rajajinagar, Bangalore",
        item_summary="Aluminum Scrap",
        asset_category="scrap",
        lots=[_lot("1", "Aluminum Scrap", quantity="1491.79", unit="MT")],
    )
    enriched = apply_display_enrichment(record)
    assert "1,492" in enriched.display_title or "1491" in enriched.display_title
    assert "Aluminium" in enriched.display_title
    assert enriched.display_material_category == "aluminium_conductor"
    assert enriched.display_total_quantity_mt == 1491.79


def test_enrich_588051_conductor_scrap():
    record = AuctionRecord(
        id="588051",
        auction_number="MSTC/588051",
        region="MUM",
        office="MUM",
        state="Maharashtra",
        location="PANVELNAVI MUMBAI",
        item_summary="Scrap Moose Conductor; Scrap Deer Conductor",
        asset_category="scrap",
        lots=[
            _lot("1", "Scrap Moose Conductor", quantity="1218.07", unit="MT"),
            _lot("2", "Scrap Deer Conductor", quantity="215.52", unit="MT"),
        ],
    )
    enriched = apply_display_enrichment(record)
    assert "Conductor" in enriched.display_title
    assert enriched.display_material_category == "transmission_scrap"
    assert enriched.display_total_quantity_mt is not None
    assert enriched.display_total_quantity_mt > 1400


def test_normalize_location_ballia():
    loc = py_normalize("CIVIL LINE BALLIA", "Uttar Pradesh", [])
    assert loc[0] == "Ballia"
    assert loc[1] == "Uttar Pradesh"
    assert loc[3] == "high"


def test_kg_to_mt_quantity_summary():
    record = AuctionRecord(
        id="x",
        auction_number="x",
        region="JPR",
        office="JPR",
        lots=[_lot("1", "Scrap", quantity="5000", unit="KG")],
    )
    enriched = apply_display_enrichment(record)
    assert enriched.display_total_quantity_mt == 5.0


def test_embedded_unit_in_quantity_field():
    record = AuctionRecord(
        id="dup",
        auction_number="dup",
        region="JPR",
        office="JPR",
        lots=[_lot("1", "Scrap", quantity="430353 KG", unit="KG")],
    )
    enriched = apply_display_enrichment(record)
    assert enriched.display_total_quantity_mt == pytest.approx(430.353, rel=0.01)
    if enriched.display_quantity_summary:
        assert "KG KG" not in enriched.display_quantity_summary.upper()


def test_location_from_office_address():
    loc = py_normalize(
        None,
        None,
        [],
        office_address="Office at New Town, Kolkata, West Bengal",
    )
    assert loc[0] == "Kolkata"
    assert loc[1] == "West Bengal"


def test_gem_long_notice_truncated_title():
    record = AuctionRecord(
        id="gem_forward:36121",
        source="gem_forward",
        auction_number="36121",
        region="MH",
        office="GeM Forward",
        state="MAHARASHTRA",
        location="Mumbai, Mumbai, MAHARASHTRA, 400086",
        item_summary=(
            "1) Bids are invited through GeM Portal for Auction of Lot No. 25A(2026) "
            "consisting of Copper/ Copper Nickle Scrap"
        ),
        lots=[_lot("1", "Lot No. 25A(2026)", quantity="1", unit="MT")],
    )
    enriched = apply_display_enrichment(record)
    assert enriched.display_title
    assert not enriched.display_title.lower().startswith("bids are invited")
    assert enriched.display_location_city == "Mumbai"


def test_eauction_timber_title():
    record = AuctionRecord(
        id="eauction:2026_MH_34847",
        source="eauction",
        auction_number="2026_MH_34847",
        region="MH",
        office="eAuction",
        state="Maharashtra",
        item_summary="e-Auction of Timber at Gadegaon Depot of Bhandara Division FDCM",
        asset_category="timber",
        lots=[
            LotRecord(
                lot_id="1",
                item_title="e-Auction of Timber at Gadegaon Depot of Bhandara Division FDCM",
            )
        ],
    )
    enriched = apply_display_enrichment(record)
    assert enriched.display_material_category == "timber"
    assert "Timber" in enriched.display_title or "timber" in enriched.display_title.lower()
