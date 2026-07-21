from unittest.mock import patch

from scraper.adapters.eauction_adapter import adapt_eauction_record
from scraper.adapters.gem_forward_adapter import adapt_gem_forward_auction
from scraper.adapters.mstc_adapter import adapt_mstc_record
from scraper.gem_forward_parser import GemForwardAuction, GemForwardItem
from scraper.models import AuctionRecord, LotRecord


def test_mstc_adapter_preserves_id_and_adds_source():
    record = AuctionRecord(
        id="587164",
        auction_number="A-1",
        region="JPR",
        office="JPR",
        lots=[LotRecord(lot_id="1", item_title="Scrap", category="Metal Scrap")],
    )
    adapted = adapt_mstc_record(record)
    assert adapted.id == "587164"
    assert adapted.source == "mstc"
    assert adapted.source_auction_id == "587164"
    assert adapted.asset_category == "scrap"


def test_gem_forward_adapter_maps_fields():
    auction = GemForwardAuction(
        auction_id="36708",
        title="Old Damaged GI Sheets",
        notice_path="/eprocure/view-auction-notice/36708/1/ABC",
        notice_token="ABC",
        state="GUJARAT",
        category="Metallic",
        seller_name="Test Seller",
        min_opening_price_inr=45721.0,
        auction_brief="Disposal of scrap",
        auction_detail="Item Description-Old Damaged GI Sheets Qty- 10 MT (Approx.)",
        items=[
            GemForwardItem(sr_no=1, item_name="Old Damaged GI Sheets", opening_price_inr=45721.0)
        ],
        detail_url="https://forwardauction.gem.gov.in/eprocure/view-auction-notice/36708/1/ABC",
    )
    record = adapt_gem_forward_auction(auction)
    assert record.id == "gem_forward:36708"
    assert record.source == "gem_forward"
    assert record.seller == "Test Seller"
    assert record.lots[0].start_price_inr == 45721.0
    assert "10 MT" in (record.item_summary or "")
    assert "GI Sheets" in (record.lots[0].lot_description_text or "")
    assert "10 MT" in (record.search_text or "")
    assert record.lots[0].item_description


def test_gem_forward_adapter_keeps_detail_over_short_lot_title():
    auction = GemForwardAuction(
        auction_id="37024",
        title="Unserviceable Drone",
        notice_path="/eprocure/view-auction-notice/37024/1/ABC",
        notice_token="ABC",
        auction_brief="Disposal of unserviceable Drone",
        auction_detail="Disposal of unserviceable Drone and related e-Waste at Bagdogra",
        items=[
            GemForwardItem(sr_no=1, item_name="Unserviceable Drone", opening_price_inr=1000.0)
        ],
    )
    record = adapt_gem_forward_auction(auction)
    assert "e-Waste" in (record.item_summary or "")
    assert record.lots[0].lot_description_text
    assert "Bagdogra" in (record.search_text or "")


def test_eauction_adapter_maps_fields():
    raw = {
        "auction_id": "90001",
        "title": "Iron Scrap",
        "organisation": "Ministry of Steel",
        "product_category": "Scrap",
        "starting_price_inr": 125000.0,
        "emd_inr": 12500.0,
        "location": "Mumbai",
        "detail_url": "https://eauction.gov.in/detail/90001",
        "document_urls": ["https://eauction.gov.in/doc/1.pdf"],
    }
    record = adapt_eauction_record(raw)
    assert record.id == "eauction:90001"
    assert record.source == "eauction"
    assert record.source_auction_id == "90001"
    assert record.seller == "Ministry of Steel"
    assert record.item_summary == "Iron Scrap"
    assert record.pre_bid_emd_amount == 12500.0
    assert record.detail_url == "https://eauction.gov.in/detail/90001"
    assert record.document_urls == ["https://eauction.gov.in/doc/1.pdf"]
    assert len(record.lots) == 1
    assert record.lots[0].item_title == "Iron Scrap"
    assert record.asset_category == "scrap"


def test_eauction_adapter_shortens_organisation_chain():
    raw = {
        "auction_id": "2026_MH_34856",
        "title": "Timber",
        "organisation": "Maharashtra||Forest Department||Nagpur Division",
        "product_category": "Timber",
        "closing_date": "2026-07-05",
        "detail_url": "https://eauction.gov.in/eAuction/app?component=view&sp=abc",
    }
    record = adapt_eauction_record(raw)
    assert record.seller == "Nagpur Division"
    assert record.closing is not None
    assert record.id == "eauction:2026_MH_34856"
