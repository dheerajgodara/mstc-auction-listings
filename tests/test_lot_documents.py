from scraper.lot_documents import (
    build_mstc_attachment_url,
    classify_document,
    extract_document_refs,
    repair_wrapped_filenames,
)
from scraper.models import LotDocument


def test_repair_wrapped_annex_filename():
    text = "Annex_7_16469_835\n6947.pdf"
    assert repair_wrapped_filenames(text) == "Annex_7_16469_8356947.pdf"


def test_repair_wrapped_photo_filename():
    text = "Photo_27_7412_8217\n660.pdf"
    assert repair_wrapped_filenames(text) == "Photo_27_7412_8217660.pdf"


def test_extract_wrapped_annex_from_documents_text():
    text = "Annexure for Lot no 1 -\nAnnex_7_16469_835\n6947.pdf"
    docs = extract_document_refs(text)
    assert len(docs) == 1
    assert docs[0].filename == "Annex_7_16469_8356947.pdf"
    assert docs[0].type == "annexure"


def test_extract_photo_pdf_filename():
    text = "Photo for Lot no 01 -\nPhoto_27_7412_8217660.pdf"
    docs = extract_document_refs(text)
    assert docs[0].filename == "Photo_27_7412_8217660.pdf"
    assert docs[0].type == "photo"


def test_classify_photo_and_annex():
    assert classify_document("Photo_27_7412_8217660.pdf") == "photo"
    assert classify_document("Annex_7_16469_8356947.pdf") == "annexure"


def test_build_mstc_attachment_url():
    url = build_mstc_attachment_url("Annex_7_16469_8356947.pdf", "annexure")
    assert "downAttachedFiles.jsp" in url
    assert "FILE_ID=Annex_7_16469_8356947.pdf" in url
    assert "doc_type=annex" in url


def test_json_model_serializes_documents():
    doc = LotDocument(
        type="annexure",
        filename="Annex_test.pdf",
        cached_url="docs/587164/Annex_test.pdf",
        thumbnail_url="thumbs/587164/1/Annex_test.webp",
        status="thumbnail_ready",
    )
    payload = doc.model_dump(mode="json")
    assert payload["filename"] == "Annex_test.pdf"
    assert payload["thumbnail_url"].startswith("thumbs/")
