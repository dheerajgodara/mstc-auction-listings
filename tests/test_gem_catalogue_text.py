"""Tests for GeM catalogue PDF/DOCX → listing body merge."""

from __future__ import annotations

from pathlib import Path

from scraper.gem_catalogue_text import (
    _clean_catalogue,
    merge_gem_catalogue_into_record,
    resolve_gem_catalogue_path,
)


def test_clean_catalogue_strips_boilerplate_and_short_noise():
    raw = (
        "General Terms and Conditions\n"
        "Page 1 of 12\n"
        "Lot consists of MS scrap mixed with copper cuttings from yard A.\n"
        "Quantity approximately 12.5 MT as per weighment.\n"
    )
    cleaned = _clean_catalogue(raw)
    assert cleaned is not None
    assert "MS scrap" in cleaned
    assert "General Terms" not in cleaned


def test_merge_gem_catalogue_fills_thin_summary(tmp_path: Path):
    pdf = tmp_path / "docs" / "gem" / "99999.pdf"
    pdf.parent.mkdir(parents=True)
    # Minimal fake PDF bytes won't extract — write plain text path via non-PDF branch.
    docx_like = tmp_path / "docs" / "gem" / "99999.txt"
    # Use .pdf name but content that falls through to utf-8 decode in _extract_bytes
    # after PDF magic check fails — write non-PDF with prose.
    prose = (
        "Auction catalogue notice for Lot 1 consisting of ferrous MS scrap "
        "approximately 25 MT located at Nashik yard ready for inspection."
    )
    pdf.write_bytes(prose.encode("utf-8"))

    record = {
        "source": "gem_forward",
        "source_auction_id": "99999",
        "item_summary": "Lot 1",
        "search_text": "Lot 1",
        "lots": [{"lot_id": "1", "item_title": "Lot 1"}],
        "warnings": [],
    }
    out = merge_gem_catalogue_into_record(record, pdf_path=pdf, make_thumb=False)
    assert "ferrous MS scrap" in (out.get("item_summary") or "")
    assert "ferrous MS scrap" in (out.get("search_text") or "")
    lot0 = out["lots"][0]
    assert "ferrous MS scrap" in (lot0.get("lot_description_text") or "")


def test_resolve_gem_catalogue_path(tmp_path: Path):
    target = tmp_path / "docs" / "gem" / "37024.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 " + b"x" * 300)
    found = resolve_gem_catalogue_path(
        public_dir=tmp_path, source_auction_id="37024", hostinger_doc_path=None
    )
    assert found == target
