"""Minimalist lane Telegram: human vocabulary, no jargon, short cards."""

from __future__ import annotations

from html import unescape

from scraper.telegram_reporter import (
    LANE_BANNED_PHRASES,
    LANE_MAX_CHARS,
    build_lane_message,
)


def _plain(html: str) -> str:
    return unescape(
        html.replace("<b>", "")
        .replace("</b>", "")
        .replace("</a>", "")
    )


def _assert_lane_ok(msg: str, *, must_contain: list[str] | None = None) -> None:
    assert msg.strip()
    assert len(msg) <= LANE_MAX_CHARS, f"too long ({len(msg)}): {msg!r}"
    plain = _plain(msg).lower()
    for banned in LANE_BANNED_PHRASES:
        assert banned not in plain, f"banned {banned!r} in {msg!r}"
    for needle in must_contain or []:
        assert needle.lower() in plain or needle in msg, f"missing {needle!r} in {msg!r}"


def test_download_progress_human():
    msg = build_lane_message(
        "download_mstc",
        "finished",
        {
            "downloaded": 28,
            "failed": 1,
            "still_need_files": 1820,
            "ready_to_process": 140,
            "live_on_site": 375,
        },
    )
    _assert_lane_ok(
        msg,
        must_contain=["Downloads (MSTC)", "+28", "1820 still need files", "140 ready to process", "Live on site: 375"],
    )


def test_parse_progress_human():
    msg = build_lane_message(
        "parse",
        "finished",
        {
            "parsed": 67,
            "skipped_fresh": 3,
            "failed": 0,
            "ready_to_process": 12,
            "ready_for_site": 390,
            "live_on_site": 375,
        },
    )
    _assert_lane_ok(
        msg,
        must_contain=["Processing", "+67", "ready to process", "ready for site", "Live on site"],
    )


def test_site_update_aged_out_expected():
    msg = build_lane_message(
        "build_deploy",
        "finished",
        {
            "published": 375,
            "live_on_site": 375,
            "ready_for_site": 390,
            "aged_out": 118,
        },
    )
    _assert_lane_ok(
        msg,
        must_contain=["Site update", "Live on site: 375", "closing already passed", "expected"],
    )
    assert "waiting" not in _plain(msg).lower() or "passed" in _plain(msg).lower()


def test_failed_has_open_log():
    msg = build_lane_message(
        "build_deploy",
        "failed",
        {
            "error": "promote refused",
            "github_run_url": "https://github.com/x/y/actions/runs/1",
        },
    )
    _assert_lane_ok(msg, must_contain=["FAILED", "promote", "Open log"])


def test_discover_minimal():
    msg = build_lane_message(
        "discover_mstc",
        "finished",
        {"listed": 2000, "new": 40, "queued_download": 40},
    )
    _assert_lane_ok(msg, must_contain=["Discover MSTC", "Found 2000", "40 new", "queued for download"])
