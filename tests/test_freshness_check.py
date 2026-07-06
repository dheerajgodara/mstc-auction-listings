from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scraper.freshness_check import check_freshness

IST = ZoneInfo("Asia/Kolkata")


def _meta_payload(*, hours_ago: float = 1.0, count: int = 1500) -> bytes:
    ran = datetime.now(IST) - timedelta(hours=hours_ago)
    return json.dumps(
        {
            "automation_ran_at": ran.isoformat(),
            "count": count,
        }
    ).encode("utf-8")


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_freshness_passes_when_recent_and_count_ok():
    with patch("scraper.freshness_check.urlopen", return_value=_FakeResp(_meta_payload())):
        result = check_freshness(base_url="https://example.com/auctions")
    assert result.passed
    assert not result.errors


def test_freshness_fails_when_stale():
    with patch(
        "scraper.freshness_check.urlopen",
        return_value=_FakeResp(_meta_payload(hours_ago=48)),
    ):
        result = check_freshness(base_url="https://example.com/auctions", max_age_hours=36)
    assert not result.passed
    assert any("old" in e for e in result.errors)


def test_freshness_fails_when_count_low():
    with patch(
        "scraper.freshness_check.urlopen",
        return_value=_FakeResp(_meta_payload(count=50)),
    ):
        result = check_freshness(base_url="https://example.com/auctions", min_count=1000)
    assert not result.passed
    assert any("count" in e for e in result.errors)
