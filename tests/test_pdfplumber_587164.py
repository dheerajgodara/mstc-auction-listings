from pathlib import Path

import pytest

from scraper.pdf_parser import (
    _match_lot_table_columns,
    _sections_from_table_row,
    extract_lots_from_pdfplumber,
    parse_lot_from_sections,
    parse_pdf_lots,
)

PDF_587164 = Path("web/public/pdfs/587164.pdf")


@pytest.fixture(scope="module")
def pdf_587164_path() -> Path:
    if not PDF_587164.is_file():
        pytest.skip(f"Missing regression PDF: {PDF_587164}")
    return PDF_587164


def test_pdfplumber_table_column_mapping():
    row = [
        "Lot Details",
        "Lot Description",
        "Lot Parameters",
        "Other Details",
        "Lot Documents",
    ]
    col_map = _match_lot_table_columns(row)
    assert col_map == {
        "lot_details_text": 0,
        "lot_description_text": 1,
        "lot_parameters_text": 2,
        "lot_other_details_text": 3,
        "lot_documents_text": 4,
    }


def test_pdfplumber_five_column_row_sections():
    row = [
        "Lot No - 1\nLot Name - Sample",
        "Description text",
        "Quantity - 1.0 LOT",
        "GST (%) - 18.0%",
        "Annexure for Lot no 1 - Annex_test.pdf",
    ]
    col_map = _match_lot_table_columns(
        ["Lot Details", "Lot Description", "Lot Parameters", "Other Details", "Lot Documents"]
    )
    sections = _sections_from_table_row(row, col_map)
    lot = parse_lot_from_sections(sections)
    assert lot["lot_details_text"].startswith("Lot No - 1")
    assert lot["lot_description_text"] == "Description text"
    assert "Quantity - 1.0 LOT" in lot["lot_parameters_text"]
    assert "GST (%) - 18.0%" in lot["lot_other_details_text"]
    assert "Annex_test.pdf" in lot["lot_documents_text"]


def test_regression_587164_pdfplumber_lot_sections(pdf_587164_path: Path):
    lots = extract_lots_from_pdfplumber(pdf_587164_path)
    assert len(lots) >= 1
    lot = lots[0]
    assert lot["lot_no"] == "1"
    assert "Lot No - 1" in lot["lot_details_text"]
    assert "Godrej" in lot["lot_details_text"]
    assert "Product Type" in lot["lot_details_text"]
    assert "Godrej Safe" in lot["lot_description_text"]
    assert "Quantity" in lot["lot_parameters_text"]
    assert "Start Price in INR" in lot["lot_parameters_text"]
    assert "Post Bid EMD" in lot["lot_parameters_text"]
    assert "GST" in lot["lot_other_details_text"]
    assert "GURDASPUR" in lot["lot_other_details_text"]
    assert "Annex_7_16469_835" in lot["lot_documents_text"]
    assert "6947.pdf" in lot["lot_documents_text"]
    assert lot["annexure_file"] == "Annex_7_16469_8356947.pdf"
    assert lot["product_type"] == "Miscellaneous"
    assert lot["category"] == "Household and Office Items"
    assert lot["bid_increment"] == 1.0
    assert lot["post_bid_emd_percent"] == 10.0
    assert lot["lot_state"] == "Punjab"


def test_regression_587164_parse_pdf_lots(pdf_587164_path: Path):
    lots = parse_pdf_lots(pdf_587164_path)
    assert len(lots) == 1
    assert lots[0]["lot_details_text"]
    assert lots[0]["lot_parameters_text"]
    assert lots[0]["lot_other_details_text"]
    assert lots[0]["lot_documents_text"]
