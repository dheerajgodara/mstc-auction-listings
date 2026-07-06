"""Tests for the enlistment / listed_at field on auction records."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.adapters.eauction_adapter import adapt_eauction_record
from scraper.adapters.gem_forward_adapter import adapt_gem_forward_auction
from scraper.adapters.mstc_adapter import adapt_mstc_record
from scraper.gem_forward_parser import GemForwardAuction
from scraper.models import AuctionRecord, LotRecord

IST = ZoneInfo("Asia/Kolkata")


def test_eauction_adapter_populates_listed_at_from_publish_date():
    publish = datetime(2026, 7, 1, 10, 30, tzinfo=IST)
    raw = {
        "auction_id": "2026_MH_34847",
        "title": "MSTC scrap",
        "publish_date": publish,
        "closing_date": datetime(2026, 7, 20, 15, 0, tzinfo=IST),
        "state": "Maharashtra",
        "organisation": "MH Dept || Something",
    }
    record = adapt_eauction_record(raw)
    assert record.listed_at is not None
    assert record.listed_at.astimezone(IST).date() == publish.date()
    assert record.listed_date == "2026-07-01"
    assert record.listed_at_source == "published_date"
    assert record.listed_at_label and record.listed_at_label.startswith("Listed ")


def test_eauction_adapter_leaves_listed_at_missing_when_no_publish_date():
    raw = {
        "auction_id": "abc",
        "title": "no date",
        "publish_date": None,
        "closing_date": None,
    }
    record = adapt_eauction_record(raw)
    assert record.listed_at is None
    assert record.listed_date is None
    assert record.listed_at_source == "missing"
    assert record.listed_at_label is None


def test_mstc_adapter_defaults_to_missing_listed_date():
    base = AuctionRecord(
        id="584985",
        auction_number="MSTC/BLR/.../14365[584985]",
        source="mstc",
        source_auction_id="584985",
        region="BLR",
        office="BLR",
        lots=[LotRecord(lot_id="1", item_title="scrap")],
    )
    adapted = adapt_mstc_record(base)
    assert adapted.listed_at is None
    assert adapted.listed_at_source == "missing"


def test_gem_forward_adapter_defaults_to_missing_listed_date():
    gem = GemForwardAuction(
        auction_id="36121",
        title="GeM auction",
        notice_path="",
        notice_token="",
        opening=datetime(2026, 7, 3, 11, 0, tzinfo=IST),
        closing=datetime(2026, 7, 10, 11, 0, tzinfo=IST),
        organisation=["Dept X"],
    )
    record = adapt_gem_forward_auction(gem)
    assert record.listed_at is None
    assert record.listed_at_source == "missing"


def test_auction_record_serializes_listed_at():
    record = AuctionRecord(
        id="test",
        auction_number="test",
        source="eauction",
        region="MH",
        office="test",
        listed_at=datetime(2026, 7, 1, 10, 30, tzinfo=IST),
        listed_date="2026-07-01",
        listed_at_source="published_date",
        listed_at_label="Listed 1 Jul 2026",
    )
    payload = record.model_dump(mode="json")
    assert payload["listed_at"].startswith("2026-07-01T10:30")
    assert payload["listed_date"] == "2026-07-01"
    assert payload["listed_at_source"] == "published_date"
    assert payload["listed_at_label"] == "Listed 1 Jul 2026"
