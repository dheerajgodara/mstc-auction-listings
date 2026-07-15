from __future__ import annotations

from pathlib import Path

from scraper.html_parser import parse_html_detail
from scraper.main import enrich_auction
from scraper.models import AuctionRecord, ExtractionStatus
from scraper.raw_store import save_raw_html


def test_parse_only_enrich_uses_disk_html(tmp_path: Path):
    # Minimal fixture with ids parse_html_detail expects
    html = """
    <html><body>
      <span id="ContentPlaceHolder1_lblAuctionNo">MSTC/TEST/1</span>
      <span id="ContentPlaceHolder1_lblOpeningDateTime">01-Jan-2026 10:00</span>
      <span id="ContentPlaceHolder1_lblCloseAt">02-Jan-2026 17:00</span>
      <span id="ContentPlaceHolder1_lblSellerName">Test Seller</span>
      <span id="ContentPlaceHolder1_lblLocation">Test City</span>
      <span id="ContentPlaceHolder1_dgLot_lblNo_0">1</span>
      <span id="ContentPlaceHolder1_dgLot_lblName_0">Scrap Lot</span>
      <span id="ContentPlaceHolder1_dgLot_lblQuantity_0">1</span>
      <span id="ContentPlaceHolder1_dgLot_Label4_0">MT</span>
    </body></html>
    """
    raw_dir = tmp_path / "raw"
    save_raw_html("mstc", "999001", html, raw_dir=raw_dir)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    # Parse-only without PDF should surface pdf error but still merge HTML fields
    base = AuctionRecord(
        id="999001",
        auction_number="MSTC/TEST/1",
        source="mstc",
        source_auction_id="999001",
        region="TEST",
        office="HO",
        status=ExtractionStatus.LISTING_ONLY,
    )
    stats: dict = {}
    record = enrich_auction(base, pdf_dir=pdf_dir, skip_pdf=True, stats=stats, mode="parse_only", raw_dir=raw_dir)
    assert stats.get("html_parsed_from_disk") == 1
    assert record.seller == "Test Seller"
    parsed = parse_html_detail(html)
    assert parsed["auction_number"] == "MSTC/TEST/1"
