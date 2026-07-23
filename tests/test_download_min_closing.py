"""Download eligibility gated on closing within the T-N archive window."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.pipeline_ledger import LedgerItem, download_eligible

IST = ZoneInfo("Asia/Kolkata")


def _pending(*, aid: str, closing: str | None) -> LedgerItem:
    now = datetime.now(IST).isoformat()
    return LedgerItem(
        stable_key=f"mstc:{aid}",
        source="mstc",
        source_auction_id=aid,
        download="pending",
        parse="pending",
        closing=closing,
        portal_doc_url="https://example.com/portal.pdf",
        first_seen_at=now,
        updated_at=now,
    )


def test_download_eligible_allows_under_runway_within_archive_window(monkeypatch):
    frozen = datetime(2026, 7, 20, 12, 0, tzinfo=IST)
    monkeypatch.setattr(
        "scraper.filters.archive_window_start",
        lambda *, now=None, retention_days=None: frozen - timedelta(days=30),
    )

    near = _pending(
        aid="near",
        closing=(frozen + timedelta(hours=11, minutes=59)).isoformat(),
    )
    edge = _pending(
        aid="edge",
        closing=(frozen + timedelta(hours=12)).isoformat(),
    )
    too_old = _pending(
        aid="old",
        closing=(frozen - timedelta(days=31)).isoformat(),
    )
    missing = _pending(aid="missing", closing=None)

    assert download_eligible(near, source="mstc") is True
    assert download_eligible(edge, source="mstc") is True
    assert download_eligible(too_old, source="mstc") is False
    assert download_eligible(missing, source="mstc") is False


def test_gem_download_eligible_uses_same_archive_window(monkeypatch):
    frozen = datetime(2026, 7, 20, 12, 0, tzinfo=IST)
    monkeypatch.setattr(
        "scraper.filters.archive_window_start",
        lambda *, now=None, retention_days=None: frozen - timedelta(days=30),
    )

    now = datetime.now(IST).isoformat()
    item = LedgerItem(
        stable_key="gem_forward:g1",
        source="gem_forward",
        source_auction_id="g1",
        download="pending",
        parse="pending",
        closing=(frozen + timedelta(hours=24)).isoformat(),
        portal_doc_url="https://example.com/doc.pdf",
        first_seen_at=now,
        updated_at=now,
    )
    assert download_eligible(item, source="gem_forward") is True
