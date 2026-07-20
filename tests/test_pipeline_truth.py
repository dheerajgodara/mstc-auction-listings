"""Ledger truth snapshot: eligible vs inventory, aged_out math."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.filters import tomorrow_min_closing_date
from scraper.pipeline_ledger import (
    LedgerItem,
    count_parse_eligible,
    count_publishable_future,
    empty_ledger,
    pipeline_truth_snapshot,
)
from scraper.pipeline_status import build_pipeline_status, truth_for_telegram

IST = ZoneInfo("Asia/Kolkata")


def _item(
    aid: str,
    *,
    download: str = "done",
    parse: str = "done",
    lots: int = 1,
    closing: str | None = None,
    host: bool = True,
) -> LedgerItem:
    now = datetime.now(IST).isoformat()
    return LedgerItem(
        stable_key=f"mstc:{aid}",
        source="mstc",
        source_auction_id=aid,
        download=download,
        parse=parse,
        lots_count=lots,
        closing=closing,
        portal_doc_url="https://example.com/portal.pdf",
        hostinger_doc_path=f"pdfs/{aid}.pdf" if host else None,
        hostinger_doc_url=f"https://example.com/pdfs/{aid}.pdf" if host else None,
        first_seen_at=now,
        updated_at=now,
    )


def test_truth_aged_out_equals_publishable_minus_future():
    tomorrow = tomorrow_min_closing_date()
    yesterday = (datetime.now(IST).date() - timedelta(days=1)).strftime("%Y-%m-%d")
    future_day = (datetime.now(IST).date() + timedelta(days=3)).strftime("%Y-%m-%d")

    ledger = empty_ledger()
    ledger.items = [
        _item("1", closing=f"{future_day}T12:00:00+05:30"),
        _item("2", closing=f"{yesterday}T12:00:00+05:30"),
        _item("3", download="pending", parse="pending", lots=0, host=False),
        _item("4", parse="pending", lots=0),  # download done, parse eligible
    ]
    snap = pipeline_truth_snapshot(ledger, pdf_disk_n=100, parsed_disk_n=10, live_n=1)
    assert snap["parse_eligible"] == 1
    assert snap["publishable_all"] == 2
    assert snap["publishable_future"] == 1
    assert snap["aged_out_parsed"] == 1
    assert snap["aged_out_parsed"] == snap["publishable_all"] - snap["publishable_future"]
    assert snap["min_closing_date"] == tomorrow
    assert snap["naive_pdf_minus_parsed"] == 90


def test_count_helpers_match_select():
    future_day = (datetime.now(IST).date() + timedelta(days=2)).strftime("%Y-%m-%d")
    ledger = empty_ledger()
    ledger.items = [
        _item("10", parse="pending", lots=0),
        _item("11", closing=f"{future_day}T10:00:00+05:30"),
    ]
    assert count_parse_eligible(ledger) == 1
    assert count_publishable_future(ledger) == 1


def test_status_telegram_subset():
    ledger = empty_ledger()
    ledger.items = [_item("1", parse="pending", lots=0)]
    status = build_pipeline_status(ledger, lane="parse", wake_reason="test")
    tg = truth_for_telegram(status)
    assert tg["parse_eligible"] == 1
    assert "aged_out_parsed" in tg
