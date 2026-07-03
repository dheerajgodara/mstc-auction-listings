from scraper.pdf_parser import (
    compute_lot_parse_warnings,
    extract_lot_sections,
    parse_lot_block,
    split_lot_blocks,
)

SAMPLE_INR_LOT = """
Lot No - 1
Lot Name - EMPTY OIL DRUM
Product Type - Container
Category - Barrel/Drum
PCB Group - Group A
Used drums in good condition.
Contact: Mr. Test 9876543210
CLICK FOR ANNEXURE
Quantity - 400.0
Unit - NO
Start Price in INR -
1802000
Bid Increment in INR -
1.0
Post Bid EMD % - 10.0
TCS (%) - 2.0
GST (%) - 18.0%
Lot Location - 220 KV S/S Pratapgarh State :Uttar Pradesh
Lot State - Uttar Pradesh
Bid Valid Till - 02-10-2026
Pre-Bid EMD Amount - Rs 17200
Photo for Lot no 01 - Photo_test.jpg
Annexure for Lot no 01 - Annex_test.pdf
"""

SAMPLE_PER_LOT = """
Lot No - 2
Lot Name - IRON ORE FINES
Product Type - Mineral
Category - Iron Ore
Premium bidding on PER basis.
Quantity - 100 MT
Start Price in PER - 85.5
Post Bid EMD % - 5.0
GST (%) - As Applicable
No document Uploaded
"""

SAMPLE_NO_DOC = """
Lot No - 3
Lot Name - SCRAP STEEL
Product Type - Metal
Category - Scrap
General scrap lot.
Quantity - 50 MT
Start Price in INR - 25000
Bid Increment in INR - 100
No document Uploaded
"""

SAMPLE_CONTACT_DESC = """
Lot No - 4
Lot Name - MACHINERY
Product Type - Equipment
Category - Industrial
For inspection contact:
Mr. Ram Kumar
Phone: 011-23456789
Email: ram@mstcindia.co.in
Quantity - 1 LOT
Start Price in INR - 500000
Annexure for Lot no 04 - Annex_04.pdf
Photo for Lot no 04 - Photo_04.jpg
"""

SAMPLE_WRAPPED_INCREMENT = """
Lot No - 5
Lot Name - TEST ITEM
Product Type - General
Category - Misc
Short description here.
Quantity - 10
Start Price in INR -
5000
Bid Increment in INR -
1.0
GST (%) - 18%
No document Uploaded
"""


def test_parse_item_wise_emd_alt_format():
    block = """
Lot No - 3
Lot Name - IRON ORE
Quantity - 100 MT
Start Price is : INR 1 /- per MT
Pre Bid EMD : INR 500 /- per MT
No document Uploaded
"""
    lot = parse_lot_block(block)
    assert lot["start_price"] == 1
    assert lot["pre_bid_emd_text"] == "INR 500 /- per MT"
    assert lot["pre_bid_emd_amount"] == 500.0


def test_split_lot_blocks():
    text = SAMPLE_INR_LOT + "\nLot No - 99\nLot Name - X\nQuantity - 1\n"
    blocks = split_lot_blocks(text)
    assert len(blocks) >= 1
    assert blocks[0].startswith("Lot No - 1")


def test_parse_wrapped_start_price():
    lot = parse_lot_block(SAMPLE_INR_LOT)
    assert lot["lot_no"] == "1"
    assert lot["start_price"] == 1802000
    assert lot["lot_name"] == "EMPTY OIL DRUM"
    assert lot["category"] == "Barrel/Drum"
    assert lot["pre_bid_emd_amount"] == 17200.0
    assert lot["annexure_file"] == "Annex_test.pdf"
    assert lot["photo_file"] == "Photo_test.jpg"
    assert lot["bid_increment"] == 1.0


def test_five_sections_present_inr():
    lot = parse_lot_block(SAMPLE_INR_LOT)
    assert "Lot No - 1" in lot["lot_details_text"]
    assert "Lot Name - EMPTY OIL DRUM" in lot["lot_details_text"]
    assert "Used drums" in lot["lot_description_text"]
    assert "CLICK FOR ANNEXURE" in lot["lot_description_text"]
    assert "Quantity - 400.0" in lot["lot_parameters_text"]
    assert "Start Price in INR - 1802000" in lot["lot_parameters_text"]
    assert "Bid Increment in INR - 1.0" in lot["lot_parameters_text"]
    assert "GST (%) - 18.0%" in lot["lot_other_details_text"]
    assert "Lot Location" in lot["lot_other_details_text"]
    assert "Annexure for Lot no 01" in lot["lot_documents_text"]
    assert "Photo for Lot no 01" in lot["lot_documents_text"]


def test_per_percentage_price():
    lot = parse_lot_block(SAMPLE_PER_LOT)
    assert lot["start_price_text"] == "Premium 85.5%"
    assert "Start Price in PER" in lot["lot_parameters_text"]
    assert "No document Uploaded" in lot["lot_documents_text"]


def test_no_document_uploaded():
    lot = parse_lot_block(SAMPLE_NO_DOC)
    assert lot["lot_documents_text"] == "No document Uploaded"
    assert "missing_lot_documents_text" not in lot["lot_parse_warnings"]


def test_annexure_and_photo_filenames():
    lot = parse_lot_block(SAMPLE_CONTACT_DESC)
    assert lot["annexure_file"] == "Annex_04.pdf"
    assert lot["photo_file"] == "Photo_04.jpg"
    assert "Annex_04.pdf" in lot["lot_documents_text"]


def test_contact_in_description():
    lot = parse_lot_block(SAMPLE_CONTACT_DESC)
    assert "Mr. Ram Kumar" in lot["lot_description_text"]
    assert "9876543210" not in lot["lot_description_text"]  # different sample
    assert "011-23456789" in lot["lot_description_text"]


def test_wrapped_bid_increment():
    lot = parse_lot_block(SAMPLE_WRAPPED_INCREMENT)
    assert lot["bid_increment"] == 1.0
    assert "Bid Increment in INR - 1.0" in lot["lot_parameters_text"]


def test_raw_sections_not_empty():
    for sample in (SAMPLE_INR_LOT, SAMPLE_PER_LOT, SAMPLE_NO_DOC, SAMPLE_CONTACT_DESC):
        lot = parse_lot_block(sample)
        assert lot["lot_details_text"].strip()
        assert lot["lot_parameters_text"].strip()
        assert lot["lot_documents_text"].strip()


def test_lot_parse_warnings_missing_docs_only_when_absent():
    lot = parse_lot_block(SAMPLE_INR_LOT)
    assert "missing_lot_details_text" not in lot["lot_parse_warnings"]
    assert "missing_lot_parameters_text" not in lot["lot_parse_warnings"]

    warnings = compute_lot_parse_warnings({
        "lot_no": "1",
        "lot_name": "X",
        "lot_details_text": "Lot No - 1",
        "lot_description_text": "",
        "lot_parameters_text": "Quantity - 1",
        "lot_documents_text": "",
        "start_price": 100,
    })
    assert "missing_lot_description_text" in warnings
    assert "missing_lot_documents_text" in warnings


def test_extract_lot_sections_marker_boundaries():
    sections = extract_lot_sections(SAMPLE_INR_LOT)
    assert sections["lot_details_text"].startswith("Lot No")
    assert "Quantity" not in sections["lot_details_text"]
    assert "Quantity" in sections["lot_parameters_text"]
