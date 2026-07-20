"""Legacy event API is retired — stubs stay quiet; lane cards are the only path."""

from __future__ import annotations

from scraper.telegram_reporter import (
    build_ai_enrichment_message,
    build_telegram_message,
    send_ai_enrichment_report,
    send_telegram_report,
)


def test_legacy_event_builders_are_empty():
    assert build_telegram_message({"download_ok": 9}, event="download_done") == ""
    assert build_ai_enrichment_message({"ready": 1}, event="complete") == ""


def test_legacy_senders_are_noop_true():
    assert send_telegram_report({"run_id": "x"}, event="download_started") is True
    assert send_telegram_report({"run_id": "x"}, event="drain_stopped") is True
    assert send_ai_enrichment_report({"ready": 1}, event="complete") is True
