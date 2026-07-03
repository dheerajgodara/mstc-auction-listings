from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.mstc_api import parse_mstc_datetime
from scraper.retention import should_keep_auction
from scraper.models import ListingApiAuction


def test_parse_mstc_datetime():
    dt = parse_mstc_datetime("03-07-2026::12:00:00")
    assert dt is not None
    assert dt.day == 3
    assert dt.month == 7
    assert dt.year == 2026
    assert dt.hour == 12


def test_retention_keeps_recent():
    auction = ListingApiAuction(
        id="1",
        text="TEST",
        opening="01-07-2026::12:00:00",
        Closing="10-07-2026::17:00:00",
        GeneralLots="Yes",
        RVSFLots="No",
        HazardousWaste="No",
        OFF_NAME="Test",
        region="JPR",
    )
    today = datetime(2026, 7, 3, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert should_keep_auction(auction, today=today) is True


def test_retention_drops_old():
    auction = ListingApiAuction(
        id="1",
        text="TEST",
        opening="01-01-2024::12:00:00",
        Closing="01-06-2026::17:00:00",
        GeneralLots="Yes",
        RVSFLots="No",
        HazardousWaste="No",
        OFF_NAME="Test",
        region="JPR",
    )
    today = datetime(2026, 7, 3, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert should_keep_auction(auction, today=today) is False
