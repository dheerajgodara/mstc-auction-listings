from scraper.merger import merge_lots
from scraper.models import AuctionRecord, ExtractionStatus


def test_merge_synthesizes_missing_section_text():
    from scraper.merger import merge_lots

    html_lots = [
        {
            "lot_no": "1",
            "name": "Godrej Safe, Revolving Chair, Wall Fan and Drinking Water Cooler etc",
            "description": "Godrej Safe, Revolving Chair, Wall Fan and Drinking Water Cooler etc. As per Lot Annexure.",
            "quantity": "1",
            "unit": "LOT",
            "location": "MAIN HARCHOWAL ROAD, QADIAN, TEHSIL BATALA, DISTT GURDASPUR State :Punjab",
            "tax_text": "As Applicable / / 18%",
        }
    ]
    pdf_lots = []
    merged = merge_lots(html_lots, pdf_lots)
    lot = merged[0]
    assert lot.lot_details_text and "Lot No - 1" in lot.lot_details_text
    assert lot.lot_parameters_text and "Quantity" in lot.lot_parameters_text
    assert lot.lot_other_details_text and "GURDASPUR" in lot.lot_other_details_text


def test_merge_html_description_fallback_for_lot_description_text():
    html_lots = [
        {
            "lot_no": "1",
            "name": "HTML Name",
            "description": "Full HTML description with contact 9876543210",
        }
    ]
    pdf_lots = [
        {
            "lot_no": "1",
            "lot_name": "PDF Name",
            "start_price": 1000,
            "lot_details_text": "Lot No - 1",
            "lot_parameters_text": "Quantity - 1",
            "lot_documents_text": "No document Uploaded",
        }
    ]
    merged = merge_lots(html_lots, pdf_lots)
    assert merged[0].lot_description_text == "Full HTML description with contact 9876543210"


def test_merge_lots_by_lot_no():
    html_lots = [
        {"lot_no": "1", "name": "HTML Name 1", "description": "desc", "quantity": "10", "unit": "NO"},
        {"lot_no": "2", "name": "HTML Name 2"},
    ]
    pdf_lots = [
        {"lot_no": "1", "lot_name": "PDF Name 1", "start_price": 1802000, "category": "Drum"},
        {"lot_no": "2", "lot_name": "PDF Name 2", "start_price": 50000},
    ]
    merged = merge_lots(html_lots, pdf_lots)
    assert len(merged) == 2
    assert merged[0].lot_id == "1"
    assert merged[0].item_title == "HTML Name 1"
    assert merged[0].start_price_inr == 1802000
    assert merged[0].category == "Drum"
    assert merged[0].item_description == "desc"


def test_merge_lots_by_index_when_no_lot_no():
    html_lots = [{"lot_no": "", "name": "Only HTML"}]
    pdf_lots = [{"lot_no": "", "lot_name": "Only PDF", "start_price": 100}]
    merged = merge_lots(html_lots, pdf_lots)
    assert len(merged) == 1
    assert merged[0].start_price_inr == 100


def test_merge_auction_summaries():
    from scraper.merger import merge_auction_record

    base = AuctionRecord(
        id="1",
        auction_number="X",
        region="JPR",
        office="JPR",
        status=ExtractionStatus.LISTING_ONLY,
    )
    html = {
        "location": "Jaipur",
        "seller": "RSMM",
        "pre_bid_emd_type": "Auction Wise",
        "pre_bid_emd_amount": 5000.0,
        "pre_bid_emd_required": True,
        "emd_parse_status": "auction_wise",
        "lots": [{"lot_no": "1", "name": "Dumper"}, {"lot_no": "2", "name": "Truck"}],
    }
    pdf = [
        {"lot_no": "1", "lot_name": "Dumper", "start_price": 1802000},
        {"lot_no": "2", "lot_name": "Truck", "start_price": 1753000},
    ]
    record = merge_auction_record(base, html_data=html, pdf_lots=pdf)
    assert record.price_summary is not None
    assert "₹" in record.price_summary
    assert record.parse_confidence in ("high", "medium")
    assert "location" not in record.missing_fields
