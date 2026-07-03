from pathlib import Path

from scraper.eauction_client import EauctionClient
from scraper.eauction_parser import parse_listing_rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "eauction"


def test_parse_listing_rows_from_synthetic_fixture():
    html = (FIXTURES / "listing_page.html").read_text(encoding="utf-8")
    rows = parse_listing_rows(html)
    assert len(rows) == 2
    first = rows[0]
    assert first["auction_id"] == "90001"
    assert first["title"] == "Iron Scrap Lot"
    assert first["publish_date"] is not None
    assert first["closing_date"] is not None
    assert first["detail_url"] is not None


def test_parse_listing_rows_from_live_bydate_fixture():
    fixture = FIXTURES / "bydate_closing_today.html"
    if not fixture.is_file():
        return
    html = fixture.read_text(encoding="utf-8")
    rows = parse_listing_rows(html)
    assert len(rows) >= 4
    first = rows[0]
    assert first["auction_id"] == "2026_MH_34856"
    assert "Timber" in (first["title"] or "")
    assert first["publish_date"] is not None
    assert first["closing_date"] is not None
    assert first["detail_url"] and "component=view" in first["detail_url"]


def test_detect_blockers_ignores_js_captcha_on_bydate_page():
    fixture = FIXTURES / "bydate_closing_today.html"
    if not fixture.is_file():
        return
    html = fixture.read_text(encoding="utf-8")
    blockers = EauctionClient().detect_blockers(html)
    assert blockers == []
