from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.document_cache import cache_lot_documents, classify_failure_reason
from scraper.lot_documents import build_mstc_attachment_urls_with_retry, doc_type_retry_order
from scraper.models import LotDocument


def test_cache_handles_failed_download_without_crashing(tmp_path: Path):
    docs = [
        LotDocument(
            type="annexure",
            filename="missing.pdf",
            source_url="https://example.invalid/missing.pdf",
        )
    ]
    session = MagicMock()
    session.get.side_effect = RuntimeError("network down")
    out_docs = cache_lot_documents(
        "587164",
        "1",
        docs,
        tmp_path / "docs",
        tmp_path / "thumbs",
        session=session,
    )
    assert len(out_docs) == 1
    assert out_docs[0].status == "failed"
    assert out_docs[0].error


def test_cache_uses_existing_file(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    thumbs_dir = tmp_path / "thumbs"
    dest = docs_dir / "587164" / "cached.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"%PDF-1.4\n" + b"x" * 600)

    docs = [
        LotDocument(
            type="document",
            filename="cached.pdf",
            source_url="https://example.invalid/should-not-fetch",
        )
    ]
    session = MagicMock()
    with patch("scraper.document_cache.generate_thumbnail", return_value=False):
        out_docs = cache_lot_documents(
            "587164",
            "1",
            docs,
            docs_dir,
            thumbs_dir,
            session=session,
        )
    assert out_docs[0].status == "thumbnail_failed"
    assert out_docs[0].cached_url == "docs/587164/cached.pdf"
    session.get.assert_not_called()


def test_doc_type_retry_order_photo():
    assert doc_type_retry_order("Photo_1_test.jpg") == ["photo", "annex", "AUC_CATALOG_FILE"]


def test_doc_type_retry_order_annex():
    assert doc_type_retry_order("Annex_7_test.pdf") == ["annex", "AUC_CATALOG_FILE"]


def test_failure_reason_classification():
    assert classify_failure_reason("HTTP 404") == "http_error"
    assert classify_failure_reason("file too small (173 bytes)") == "too_small"
    assert classify_failure_reason("max-docs-per-run") == "budget_exhausted"


def test_download_retries_doc_types(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    thumbs_dir = tmp_path / "thumbs"
    session = MagicMock()

    responses = []
    for status in (404, 200):
        resp = MagicMock()
        resp.status_code = status
        resp.content = b"%PDF-1.4\n" + b"x" * 600 if status == 200 else b"err"
        resp.headers = {"Content-Type": "application/pdf"}
        responses.append(resp)
    session.get.side_effect = responses

    docs = [
        LotDocument(
            type="photo",
            filename="Photo_1_test.pdf",
            source_url="https://example.invalid/photo",
        )
    ]
    with patch("scraper.document_cache.generate_thumbnail", return_value=False):
        out_docs = cache_lot_documents(
            "587164",
            "1",
            docs,
            docs_dir,
            thumbs_dir,
            session=session,
        )
    assert out_docs[0].status == "thumbnail_failed"
    assert session.get.call_count == 2
    assert len(build_mstc_attachment_urls_with_retry("Photo_1_test.pdf")) == 3
