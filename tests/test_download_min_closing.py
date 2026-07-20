"""Download eligibility gated on closing >= now + 12h runway."""

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


def test_download_eligible_requires_12h_runway(monkeypatch):
    frozen = datetime(2026, 7, 20, 12, 0, tzinfo=IST)

    def _resolve(force_min_closing_date=None, *, now=None, hours_ahead=None):
        from scraper.filters import min_closing_datetime, parse_min_closing_boundary

        if force_min_closing_date:
            return parse_min_closing_boundary(force_min_closing_date)
        return min_closing_datetime(now=frozen, hours_ahead=12)

    monkeypatch.setattr("scraper.filters.resolve_min_closing", _resolve)

    near = _pending(
        aid="near",
        closing=(frozen + timedelta(hours=11, minutes=59)).isoformat(),
    )
    edge = _pending(
        aid="edge",
        closing=(frozen + timedelta(hours=12)).isoformat(),
    )
    missing = _pending(aid="missing", closing=None)

    assert download_eligible(near, source="mstc") is False
    assert download_eligible(edge, source="mstc") is True
    assert download_eligible(missing, source="mstc") is False


def test_gem_download_eligible_uses_same_runway(monkeypatch):
    frozen = datetime(2026, 7, 20, 12, 0, tzinfo=IST)

    def _resolve(force_min_closing_date=None, *, now=None, hours_ahead=None):
        from scraper.filters import min_closing_datetime

        return min_closing_datetime(now=frozen, hours_ahead=12)

    monkeypatch.setattr("scraper.filters.resolve_min_closing", _resolve)

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
