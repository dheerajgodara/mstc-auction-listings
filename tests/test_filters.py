from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.filters import (
    apply_future_filter,
    min_closing_datetime,
    parse_min_closing_date,
    passes_min_closing,
    resolve_min_closing,
)
from scraper.models import AuctionRecord, LotRecord

IST = ZoneInfo("Asia/Kolkata")


def test_parse_min_closing_date_ist():
    dt = parse_min_closing_date("2026-07-04")
    assert dt == datetime(2026, 7, 4, 0, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_min_closing_datetime_hours_ahead():
    now = datetime(2026, 7, 20, 18, 0, tzinfo=IST)
    boundary = min_closing_datetime(now=now, hours_ahead=12)
    assert boundary == datetime(2026, 7, 21, 6, 0, tzinfo=IST)


def test_resolve_min_closing_force_date_and_default():
    now = datetime(2026, 7, 20, 18, 0, tzinfo=IST)
    forced = resolve_min_closing("2026-07-22", now=now)
    assert forced == datetime(2026, 7, 22, 0, 0, tzinfo=IST)
    default = resolve_min_closing(now=now, hours_ahead=12)
    assert default == datetime(2026, 7, 21, 6, 0, tzinfo=IST)


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


def test_apply_future_filter_12h_runway():
    now = datetime(2026, 7, 20, 12, 0, tzinfo=IST)
    boundary = min_closing_datetime(now=now, hours_ahead=12)
    records = [
        AuctionRecord(
            id="near",
            auction_number="near",
            region="JPR",
            office="JPR",
            closing=now + timedelta(hours=11, minutes=59),
            lots=[LotRecord(lot_id="1", item_title="near")],
        ),
        AuctionRecord(
            id="edge",
            auction_number="edge",
            region="JPR",
            office="JPR",
            closing=now + timedelta(hours=12),
            lots=[LotRecord(lot_id="1", item_title="edge")],
        ),
        AuctionRecord(
            id="far",
            auction_number="far",
            region="JPR",
            office="JPR",
            closing=now + timedelta(hours=24),
            lots=[LotRecord(lot_id="1", item_title="far")],
        ),
    ]
    kept, stats = apply_future_filter(records, boundary)
    assert stats["excluded_past_closing"] == 1
    assert stats["kept"] == 2
    assert {r.id for r in kept} == {"edge", "far"}


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


def test_partition_closing_lanes_same_day_goes_to_archive():
    from scraper.filters import is_archive_eligible, is_live_eligible, partition_closing_lanes

    now = datetime(2026, 7, 23, 14, 0, tzinfo=IST)
    boundary = min_closing_datetime(now=now, hours_ahead=12)
    records = [
        AuctionRecord(
            id="19431",
            auction_number="MSTC/JPR/All India Radio/2/Jodhpur/26-27/19431",
            region="JPR",
            office="JPR",
            closing=datetime(2026, 7, 23, 17, 0, tzinfo=IST),
            opening=datetime(2026, 7, 23, 12, 0, tzinfo=IST),
            lots=[LotRecord(lot_id="1", item_title="Copper Scrap")],
        ),
        AuctionRecord(
            id="future",
            auction_number="future",
            region="JPR",
            office="JPR",
            closing=now + timedelta(days=2),
            lots=[LotRecord(lot_id="1", item_title="future")],
        ),
        AuctionRecord(
            id="ancient",
            auction_number="ancient",
            region="JPR",
            office="JPR",
            closing=now - timedelta(days=45),
            lots=[LotRecord(lot_id="1", item_title="old")],
        ),
    ]
    live, archive, stats = partition_closing_lanes(records, min_closing=boundary, now=now)
    assert {r.id for r in live} == {"future"}
    assert {r.id for r in archive} == {"19431"}
    assert stats["excluded_too_old"] == 1
    assert is_archive_eligible(records[0].closing, now=now, min_closing=boundary)
    assert not is_live_eligible(records[0].closing, now=now, min_closing=boundary)
