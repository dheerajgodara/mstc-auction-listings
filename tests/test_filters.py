from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.filters import apply_future_filter, parse_min_closing_date, passes_min_closing
from scraper.models import AuctionRecord, LotRecord


def test_parse_min_closing_date_ist():
    dt = parse_min_closing_date("2026-07-04")
    assert dt == datetime(2026, 7, 4, 0, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_apply_future_filter_excludes_past_and_missing():
    ist = ZoneInfo("Asia/Kolkata")
    records = [
        AuctionRecord(
            id="1",
            auction_number="1",
            region="JPR",
            office="JPR",
            closing=datetime(2026, 7, 3, 23, 59, tzinfo=ist),
            lots=[LotRecord(lot_id="1", item_title="past")],
        ),
        AuctionRecord(
            id="2",
            auction_number="2",
            region="JPR",
            office="JPR",
            closing=datetime(2026, 7, 4, 0, 0, tzinfo=ist),
            lots=[LotRecord(lot_id="1", item_title="today midnight")],
        ),
        AuctionRecord(
            id="3",
            auction_number="3",
            region="JPR",
            office="JPR",
            closing=datetime(2026, 7, 5, 12, 0, tzinfo=ist),
            lots=[LotRecord(lot_id="1", item_title="future")],
        ),
        AuctionRecord(
            id="4",
            auction_number="4",
            region="JPR",
            office="JPR",
            closing=None,
            lots=[LotRecord(lot_id="1", item_title="missing")],
        ),
    ]
    min_closing = parse_min_closing_date("2026-07-04")
    kept, stats = apply_future_filter(records, min_closing)
    assert stats["before_filter"] == 4
    assert stats["excluded_past_closing"] == 1
    assert stats["excluded_missing_closing"] == 1
    assert stats["kept"] == 2
    assert {r.id for r in kept} == {"2", "3"}


def test_passes_min_closing_naive_datetime():
    record = AuctionRecord(
        id="1",
        auction_number="1",
        region="JPR",
        office="JPR",
        closing=datetime(2026, 7, 4, 10, 0),
        lots=[],
    )
    assert passes_min_closing(record, parse_min_closing_date("2026-07-04")) is True
