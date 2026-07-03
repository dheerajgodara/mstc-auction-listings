from scraper.merger import build_lot_count_warnings, merge_auction_record
from scraper.models import AuctionRecord, ExtractionStatus
from scraper.pdf_parser import split_lot_blocks
from scraper.price import resolve_auction_price

PERCENTAGE_BLOCK = """
Lot No - 1
Lot Name - Test Mine
Category - Mock Auction Test Block, bidding to be done in percentage of Value of Mineral Despatched
Quantity - 1 BLOCK
"""

ANNEXURE_BLOCK = """
Lot No - 2
Lot Name - Coal Block
Lot Name - Block A
Start Price in INR - 
Rate to be quoted as per notice
"""

TERMS_WITH_LOT_REF = """
Lot No - 1
Lot Name - REAL ITEM
Product Type - Ore
Quantity - 1 MT
Start Price in INR - 50000
Terms and Conditions
Refer to Lot No - 99 for dispute resolution without lot name field.
Lot No - 99
only a reference in terms
"""


def test_percentage_based_not_missing_start_price():
    base = AuctionRecord(
        id="314254",
        auction_number="X",
        region="HO",
        office="HO",
        status=ExtractionStatus.LISTING_ONLY,
    )
    html = {
        "location": "ANDAMAN",
        "seller": "TEST",
        "lots": [{
            "lot_no": "1",
            "name": "Test Mine",
            "description": "Mock Auction Test Block, bidding to be done in percentage of Value of Mineral Despatched",
        }],
    }
    record = merge_auction_record(
        base,
        html_data=html,
        pdf_lots=[{"lot_no": "1", "lot_name": "Test Mine", "category": html["lots"][0]["description"]}],
    )
    assert record.price_parse_status == "percentage_based"
    assert record.price_summary == "Percentage-based bidding"
    assert "start_price" not in record.missing_fields
    assert record.parse_confidence in ("high", "medium")


def test_as_per_annexure_not_disclosed():
    status, summary = resolve_auction_price(
        [],
        pdf_lots=[{"lot_name": "Block", "category": "rate to be quoted as per notice"}],
    )
    assert status == "not_disclosed"
    assert summary == "See PDF for price"


def test_numeric_range_summary():
    from scraper.models import LotRecord

    lots = [
        LotRecord(lot_id="1", item_title="A", start_price_inr=1000, start_price=1000),
        LotRecord(lot_id="2", item_title="B", start_price_inr=5000, start_price=5000),
    ]
    status, summary = resolve_auction_price(lots)
    assert status == "range"
    assert "Floor" in (summary or "")
    assert "₹" in (summary or "")


def test_empty_catalogue_low_confidence():
    base = AuctionRecord(
        id="582181",
        auction_number="X",
        region="HYD",
        office="HYD",
        location="Hyderabad",
        seller="HMDA",
        status=ExtractionStatus.LISTING_ONLY,
    )
    record = merge_auction_record(base, html_data={"lots": []}, pdf_lots=[])
    assert record.parse_confidence == "low"
    assert "lots" in record.missing_fields
    assert any("No lots found" in w for w in record.warnings)


def test_terms_lot_no_not_parsed_as_block():
    blocks = split_lot_blocks(TERMS_WITH_LOT_REF)
    assert len(blocks) == 1
    assert blocks[0].startswith("Lot No - 1")
    assert "REAL ITEM" in blocks[0]


def test_per_premium_price_percentage():
    from scraper.pdf_parser import parse_lot_block

    block = """
Lot No - 1
Lot Name - BLOCK A
Product Type - Mineral
Category - As per NIT and Tender Document
Quantity - 1.0 BLOCK
Start Price in PER - 25
Bid Increment in PER - 0.0
"""
    lot = parse_lot_block(block)
    assert lot["start_price_text"] == "Premium 25%"
    status, summary = resolve_auction_price([{"start_price_text": lot["start_price_text"], "category": lot["category"]}])
    assert status == "percentage_based"
    assert summary == "Percentage-based bidding"


def test_lot_count_mismatch_warning():
    warnings = build_lot_count_warnings(200, 520)
    assert any("lot_count_mismatch" in w for w in warnings)
    assert "html=200" in warnings[0]
    assert "pdf=520" in warnings[0]
