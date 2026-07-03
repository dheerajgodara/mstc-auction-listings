from scraper.lot_sections import synthesize_lot_sections
from scraper.models import LotRecord


def test_synthesize_sections_from_structured_fields():
    lot = LotRecord(
        lot_id="1",
        item_title="Godrej Safe, Revolving Chair, Wall Fan and Drinking Water Cooler etc",
        item_description="Godrej Safe, Revolving Chair, Wall Fan and Drinking Water Cooler etc. As per Lot Annexure.",
        quantity="1.0 LOT",
        start_price=1.0,
        bid_increment=1.0,
        post_bid_emd_percent=10.0,
        gst="18.0%",
        location="MAIN HARCHOWAL ROAD, QADIAN, TEHSIL BATALA, DISTT GURDASPUR State :Punjab",
        lot_state="Punjab",
        bid_valid_till="01-10-2026",
        annexure_file="Annex_7_16469_8356947.pdf",
    )
    out = synthesize_lot_sections(lot)
    assert "Lot No - 1" in out.lot_details_text
    assert "Godrej Safe" in out.lot_details_text
    assert "Quantity - 1.0 LOT" in out.lot_parameters_text
    assert "Start Price in INR - 1" in out.lot_parameters_text
    assert "GST (%) - 18.0%" in out.lot_other_details_text
    assert "GURDASPUR" in out.lot_other_details_text
    assert "Annex_7_16469_8356947.pdf" in out.lot_documents_text


def test_synthesize_preserves_existing_raw_sections():
    lot = LotRecord(
        lot_id="1",
        item_title="X",
        lot_details_text="Lot No - 1\nLot Name - X",
        lot_parameters_text="Quantity - 1",
        lot_other_details_text="GST (%) - 5%",
        lot_documents_text="No document Uploaded",
    )
    out = synthesize_lot_sections(lot)
    assert out.lot_details_text == "Lot No - 1\nLot Name - X"
    assert out.lot_other_details_text == "GST (%) - 5%"
