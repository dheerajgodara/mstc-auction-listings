"""Quality bar for plain-language Telegram messages (readable on phone)."""

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
    return unescape(
        html.replace("<b>", "")
        .replace("</b>", "")
        .replace("<a href=", " ")
        .replace("</a>", "")
    )


def _assert_compact(msg: str, *, must_contain: list[str] | None = None) -> None:
    assert msg.strip(), "empty message"
    assert len(msg) <= MAX_MESSAGE_CHARS, f"too long ({len(msg)}): {msg!r}"
    assert msg.count("\n") <= 7, f"too many lines: {msg!r}"
    for banned in ("Min closing", "Started:", "Finished:", "Run:", "Comparison", "Deep Scrape", "Prompt/schema"):
        assert banned not in msg, f"banned noise {banned!r} in {msg!r}"
    plain = _plain(msg)
    for needle in must_contain or []:
        assert needle in msg or needle in plain, f"missing {needle!r} in {msg!r}"


def test_q1_download_done_explains_zero_and_queue():
    empty = build_telegram_message(
        {
            "download_ok": 0,
            "download_failed": 0,
            "wall_seconds": 34,
            "ledger": {
                "download": {"done": 1801, "pending": 0},
                "parse": {"done": 1698, "pending": 31},
                "deploy_ready": 1697,
            },
            "github_run_url": "https://github.com/x/y/actions/runs/1",
        },
        event="download_done",
    )
    _assert_compact(
        empty,
        must_contain=["Download finished", "Nothing new", "waiting to process 31", "ready for site 1697"],
    )

    busy = build_telegram_message(
        {
            "download_ok": 990,
            "download_failed": 0,
            "wall_seconds": 4740,
            "ledger": {
                "download": {"done": 1437, "pending": 0},
                "parse": {"done": 200, "pending": 1237},
                "deploy_ready": 200,
            },
            "github_run_url": "https://github.com/x/y/actions/runs/1",
        },
        event="download_done",
    )
    _assert_compact(busy, must_contain=["Download finished", "Downloaded 990", "waiting to process 1237"])


def test_q2_download_failed_shows_error_not_essay():
    msg = build_telegram_message(
        {"errors": ["SSH timeout connecting to host"], "ledger": {"download": {"pending": 50}}},
        event="download_failed",
    )
    _assert_compact(msg, must_contain=["Download failed", "SSH"])


def test_q3_drain_done_and_stopped():
    done = build_telegram_message(
        {
            "cycles_completed": 2,
            "parse_backlog_end": 0,
            "ledger": {
                "download": {"done": 1801},
                "parse": {"done": 1729, "pending": 0},
                "deploy_ready": 1728,
            },
        },
        event="drain_done",
    )
    _assert_compact(
        done,
        must_contain=["Catch-up finished", "2 rounds", "nothing left to process"],
    )
    stopped = build_telegram_message(
        {"errors": ["parse retries exhausted: boom"], "ledger": {"parse": {"pending": 80}}},
        event="drain_stopped",
    )
    _assert_compact(stopped, must_contain=["Catch-up stopped", "boom"])


def test_q4_deploy_and_parse_done():
    deploy = build_telegram_message({"auctions": 1969}, event="deploy_done")
    _assert_compact(deploy, must_contain=["Site updated", "1969", "live"])
    skipped = build_telegram_message(
        {"deploy_skipped_unchanged": True, "auctions": 1969},
        event="deploy_done",
    )
    _assert_compact(skipped, must_contain=["skipped", "No change"])
    parse = build_telegram_message(
        {
            "parse_ok": 25,
            "parse_failed": 6,
            "auctions": 2061,
            "ledger": {
                "download": {"done": 1801},
                "parse": {"done": 1723, "pending": 6},
                "deploy_ready": 1722,
            },
        },
        event="parse_done",
    )
    _assert_compact(
        parse,
        must_contain=["Processing finished", "Processed 25", "6 failed", "site list now 2061"],
    )


def test_q5_retry_and_ai_messages():
    retry = build_telegram_message(
        {"retry_attempt": 1, "wait_minutes": 15},
        event="download_retry_scheduled",
    )
    _assert_compact(retry, must_contain=["retry", "15"])
    exhausted = build_telegram_message({}, event="download_retries_exhausted")
    _assert_compact(exhausted, must_contain=["retries", "6-hour"])
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
    _assert_compact(ai, must_contain=["AI enrichment finished", "40", "ready"])
    assert "Prompt/schema" not in ai
    assert "Top Selected" not in ai


def test_q6_quiet_events_not_sent():
    assert "download_started" in QUIET_EVENTS
    assert "drain_cycle" in QUIET_EVENTS
    assert send_telegram_report({"run_id": "x"}, event="download_started") is True
    assert send_telegram_report({"run_id": "x"}, event="parse_selection") is True


def test_q7_legacy_refresh_compact():
    msg = build_telegram_message(
        {
            "total_auctions": 1900,
            "by_source": {"mstc": 1800, "eauction": 60, "gem_forward": 40},
        },
        event="success",
    )
    _assert_compact(msg, must_contain=["Refresh finished", "1900", "mstc"])
