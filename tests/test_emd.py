from scraper.html_parser import parse_html_detail
from scraper.merger import merge_auction_record
from scraper.models import AuctionRecord, ExtractionStatus
from scraper.pdf_parser import _parse_pdf_emd_header, parse_lot_block

NOT_REQUIRED_HTML = """
<html><body>
<span id="ContentPlaceHolder1_lblEmdType">Not a Auto Prebid EMD Auction</span>
<span id="ContentPlaceHolder1_lblEmdAmt"></span>
<span id="ContentPlaceHolder1_lblLocation">Jaipur</span>
<span id="ContentPlaceHolder1_dgLot_lblNo_0">1</span>
<span id="ContentPlaceHolder1_dgLot_lblName_0">Scrap Item</span>
</body></html>
"""



def test_format_inr_indian_grouping():
    from scraper.emd import format_inr_amount, format_indian_number

    assert format_indian_number(17200) == "17,200"
    assert format_indian_number(100000) == "1,00,000"
    assert format_indian_number(500100000) == "50,01,00,000"
    assert format_inr_amount(500100000) == "₹50,01,00,000"
    assert format_inr_amount(4580000) == "₹45,80,000"
    assert format_inr_amount(1234.56, decimals=2) == "₹1,234.56"

    data = parse_html_detail(NOT_REQUIRED_HTML)
    assert data["pre_bid_emd_required"] is False
    assert data["emd_parse_status"] == "not_required"

    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    record = merge_auction_record(
        base,
        html_data={**data, "location": "Jaipur", "lots": data["lots"]},
        pdf_lots=[{"lot_no": "1", "lot_name": "Scrap Item", "start_price": 1000}],
    )
    assert record.emd_parse_status == "not_required"
    assert record.emd_summary == "No auto pre-bid EMD"
    assert "emd" not in record.missing_fields
    assert record.parse_confidence in ("high", "medium")


def test_pdf_header_auction_wise_emd():
    header = """
Pre-Bid EMD: Auction Wise EMD
Pre-Bid EMD Amount - Rs 100000
Closing Date - 10-07-2026
"""
    emd = _parse_pdf_emd_header(header)
    assert emd["emd_parse_status"] == "auction_wise"
    assert emd["pre_bid_emd_required"] is True
    assert emd["pre_bid_emd_amount"] == 100000.0


def test_pdf_lot_pre_bid_emd_amount():
    block = """
Lot No - 1
Lot Name - DRUM
Pre-Bid EMD Amount - Rs 17200
"""
    lot = parse_lot_block(block)
    assert lot["pre_bid_emd_amount"] == 17200.0


def test_pdf_lot_pre_bid_emd_text_per_mt():
    block = """
Lot No - 3
Lot Name - IRON ORE
Pre Bid EMD : INR 1 /- per MT
"""
    lot = parse_lot_block(block)
    assert lot["pre_bid_emd_text"] == "INR 1 /- per MT"
    assert lot["pre_bid_emd_amount"] == 1.0


def test_merger_confidence_not_required():
    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    html = {
        "location": "Jaipur",
        "seller": "Test Co",
        "pre_bid_emd_type": "Not a Auto Prebid EMD Auction",
        "pre_bid_emd_required": False,
        "emd_parse_status": "not_required",
        "lots": [{"lot_no": "1", "name": "Item"}],
    }
    record = merge_auction_record(
        base,
        html_data=html,
        pdf_lots=[{"lot_no": "1", "lot_name": "Item", "start_price": 50000}],
    )
    assert record.parse_confidence == "high"
    assert "emd" not in record.missing_fields


def test_merger_confidence_item_wise_lot_emd():
    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    html = {
        "location": "Jaipur",
        "seller": "Test Co",
        "pre_bid_emd_type": "Item Wise",
        "pre_bid_emd_required": True,
        "emd_parse_status": "item_wise",
        "lots": [{"lot_no": "1", "name": "Item"}],
    }
    record = merge_auction_record(
        base,
        html_data=html,
        pdf_lots=[{
            "lot_no": "1",
            "lot_name": "Item",
            "start_price": 1000,
            "pre_bid_emd_amount": 17200.0,
        }],
    )
    assert record.emd_parse_status == "item_wise"
    assert record.parse_confidence == "high"
    assert "emd" not in record.missing_fields
    assert "from ₹17,200" in (record.emd_summary or "")


def test_item_wise_without_parsed_lot_emd_stays_item_wise():
    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    html = {
        "location": "Jaipur",
        "seller": "Test Co",
        "pre_bid_emd_type": "Item Wise",
        "pre_bid_emd_required": True,
        "emd_parse_status": "item_wise",
        "lots": [{"lot_no": "1", "name": "Item"}],
    }
    record = merge_auction_record(
        base,
        html_data=html,
        pdf_lots=[{"lot_no": "1", "lot_name": "Item", "start_price": 1000}],
    )
    assert record.emd_parse_status == "item_wise"
    assert record.emd_summary == "Pre-bid EMD: item-wise"
    assert "emd" not in record.missing_fields


def test_missing_emd_but_lots_have_numeric_emd_becomes_item_wise():
    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    record = merge_auction_record(
        base,
        html_data={
            "location": "Jaipur",
            "seller": "Test Co",
            "pre_bid_emd_type": "Unknown",
            "pre_bid_emd_required": True,
            "emd_parse_status": "missing",
            "lots": [{"lot_no": "1", "name": "Item"}],
        },
        pdf_lots=[{
            "lot_no": "1",
            "lot_name": "Item",
            "start_price": 1000,
            "pre_bid_emd_amount": 5000.0,
        }],
    )
    assert record.emd_parse_status == "item_wise"
    assert "emd" not in record.missing_fields


def test_missing_emd_but_lots_have_emd_text_becomes_item_wise():
    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    record = merge_auction_record(
        base,
        html_data={
            "location": "Jaipur",
            "seller": "Test Co",
            "pre_bid_emd_required": True,
            "emd_parse_status": "missing",
            "lots": [{"lot_no": "1", "name": "Item"}],
        },
        pdf_lots=[{
            "lot_no": "1",
            "lot_name": "Item",
            "start_price": 1000,
            "lot_parameters_text": "Pre-bid EMD (4% of Floor Price) Rs 100 per MT",
        }],
    )
    assert record.emd_parse_status == "item_wise"
    assert "emd" not in record.missing_fields


def test_truly_missing_required_emd_remains_missing():
    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    record = merge_auction_record(
        base,
        html_data={
            "location": "Jaipur",
            "seller": "Test Co",
            "pre_bid_emd_required": True,
            "emd_parse_status": "unknown",
            "lots": [{"lot_no": "1", "name": "Item"}],
        },
        pdf_lots=[{"lot_no": "1", "lot_name": "Item", "start_price": 1000}],
    )
    assert record.emd_parse_status == "missing"
    assert "emd" in record.missing_fields
