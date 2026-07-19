from __future__ import annotations

from pathlib import Path

import pytest

from scraper.gem_forward_parser import (
    merge_auction,
    parse_detail_page,
    parse_listing_page,
    parse_listing_record_count,
    parse_rules_page,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gem_forward"


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "listing_page1.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html() -> str:
    return (FIXTURES / "detail_36708.html").read_text(encoding="utf-8")


@pytest.fixture
def rules_html() -> str:
    return (FIXTURES / "rules_36708.html").read_text(encoding="utf-8")


def test_listing_record_count(listing_html: str) -> None:
    assert parse_listing_record_count(listing_html) == 107


def test_parse_listing_page(listing_html: str) -> None:
    listings = parse_listing_page(listing_html)
    assert len(listings) == 10
    first = listings[0]
    assert first.auction_id == "36708"
    assert first.title == "Old Damaged GI Sheets"
    assert first.state == "GUJARAT"
    assert first.pincode == "393110"
    assert first.opening is not None
    assert first.closing is not None
    assert "view-auction-notice/36708" in first.notice_path


def test_parse_detail_page(detail_html: str) -> None:
    detail = parse_detail_page(detail_html)
    assert detail["category"] == "Metallic"
    assert detail["auction_brief"] == "Old Damaged GI Sheets"
    assert "GI Sheets" in (detail["auction_detail"] or "")
    assert detail["emd_required"] is False
    assert detail["rules_path"] is not None


def test_parse_rules_page(rules_html: str) -> None:
    items = parse_rules_page(rules_html)
    assert len(items) == 1
    assert items[0].item_name == "Old Damaged GI Sheets"
    assert items[0].opening_price_inr == 45721.0
    assert items[0].increment_price_inr == 1000.0


def test_parse_listing_dates_without_blink_wrapper() -> None:
    """GeM Live listings often omit span.blink; dates live in start-date/end-date only."""
    html = """
    <input type="hidden" name="recordCount" id="recordCount" value="1" />
    <div class="eproc-listing-main">
      <div class="listing-content">
        <div class="index"><label>1) Auction ID : 36492</label></div>
        <div class="brief"><p><a href="/eprocure/view-auction-notice/36492/0/ABC" class="brief">Servers</a></p></div>
        <div class="listing-date-info">
          <span class="">
            <span class="start-date">Start Date : 30/07/2026 10:00:00</span>
            <span class="end-date">End Date : 31/07/2026 17:00:00</span>
          </span>
        </div>
      </div>
    </div>
    """
    listings = parse_listing_page(html)
    assert len(listings) == 1
    assert listings[0].auction_id == "36492"
    assert listings[0].opening is not None
    assert listings[0].closing is not None
    assert listings[0].closing.day == 31

