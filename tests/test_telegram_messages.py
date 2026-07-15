"""Quality bar for compact Telegram messages (readable on phone)."""

from __future__ import annotations

from html import unescape

from scraper.telegram_reporter import (
    MAX_MESSAGE_CHARS,
    QUIET_EVENTS,
    build_ai_enrichment_message,
    build_telegram_message,
    send_telegram_report,
)


def _plain(html: str) -> str:
    return unescape(html.replace("<b>", "").replace("</b>", "").replace("<a href=", " ").replace("</a>", ""))


def _assert_compact(msg: str, *, must_contain: list[str] | None = None) -> None:
    assert msg.strip(), "empty message"
    assert len(msg) <= MAX_MESSAGE_CHARS, f"too long ({len(msg)}): {msg!r}"
    # Roughly short: not more than ~8 lines
    assert msg.count("\n") <= 7, f"too many lines: {msg!r}"
    # No legacy dump noise
    for banned in ("Min closing", "Started:", "Finished:", "Run:", "Comparison", "Deep Scrape", "Prompt/schema"):
        assert banned not in msg, f"banned noise {banned!r} in {msg!r}"
    for needle in must_contain or []:
        assert needle in msg or needle in _plain(msg), f"missing {needle!r} in {msg!r}"


def test_q1_download_done_is_short_and_clear():
    msg = build_telegram_message(
        {
            "download_ok": 990,
            "download_failed": 0,
            "wall_seconds": 4740,
            "ledger": {"download": {"done": 1437, "pending": 0}, "parse": {"done": 200, "pending": 1237}},
            "github_run_url": "https://github.com/x/y/actions/runs/1",
        },
        event="download_done",
    )
    _assert_compact(msg, must_contain=["Download", "done", "990", "ok"])
    assert "1237" in msg or "Parse" in msg


def test_q2_download_failed_shows_error_not_essay():
    msg = build_telegram_message(
        {"errors": ["SSH timeout connecting to host"], "ledger": {"download": {"pending": 50}}},
        event="download_failed",
    )
    _assert_compact(msg, must_contain=["Download", "failed", "SSH"])


def test_q3_drain_done_and_stopped():
    done = build_telegram_message(
        {"cycles_completed": 12, "parse_backlog_end": 0, "ledger": {"parse": {"done": 1200, "pending": 0}}},
        event="drain_done",
    )
    _assert_compact(done, must_contain=["Drain", "done", "12"])
    stopped = build_telegram_message(
        {"errors": ["parse retries exhausted: boom"], "ledger": {"parse": {"pending": 80}}},
        event="drain_stopped",
    )
    _assert_compact(stopped, must_contain=["Drain", "stopped", "boom"])


def test_q4_deploy_and_parse_done():
    deploy = build_telegram_message({"auctions": 1969}, event="deploy_done")
    _assert_compact(deploy, must_contain=["Deploy", "1969"])
    skipped = build_telegram_message({"deploy_skipped_unchanged": True, "auctions": 1969}, event="deploy_done")
    _assert_compact(skipped, must_contain=["skipped"])
    parse = build_telegram_message(
        {"parse_ok": 100, "parse_failed": 2, "auctions": 1970, "ledger": {"parse": {"done": 300, "pending": 900}}},
        event="parse_done",
    )
    _assert_compact(parse, must_contain=["Parse", "100", "ok"])


def test_q5_retry_and_ai_messages():
    retry = build_telegram_message({"retry_attempt": 1, "wait_minutes": 15}, event="download_retry_scheduled")
    _assert_compact(retry, must_contain=["retry", "15"])
    exhausted = build_telegram_message({}, event="download_retries_exhausted")
    _assert_compact(exhausted, must_contain=["retries"])
    ai = build_ai_enrichment_message(
        {
            "ready": 40,
            "failed": 2,
            "skipped": 5,
            "processed": 47,
            "budget": {"remaining_today": 210},
            "selection": {"remaining_after_selection": 800},
            "duration_sec": 420,
            "github_run_url": "https://github.com/x/y/actions/runs/9",
        },
        event="complete",
    )
    _assert_compact(ai, must_contain=["AI", "40", "ready"])
    assert "Prompt/schema" not in ai
    assert "Top Selected" not in ai


def test_q6_quiet_events_not_sent():
    assert "download_started" in QUIET_EVENTS
    assert "drain_cycle" in QUIET_EVENTS
    assert send_telegram_report({"run_id": "x"}, event="download_started") is True
    assert send_telegram_report({"run_id": "x"}, event="parse_selection") is True


def test_q7_legacy_refresh_compact():
    msg = build_telegram_message(
        {"total_auctions": 1900, "by_source": {"mstc": 1800, "eauction": 60, "gem_forward": 40}},
        event="success",
    )
    _assert_compact(msg, must_contain=["Refresh", "1900", "mstc"])
