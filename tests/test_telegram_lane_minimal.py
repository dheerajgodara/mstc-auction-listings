"""Golden HTML lane cards: human vocabulary, severity, typography."""

from __future__ import annotations

from html import unescape

from scraper.telegram_reporter import (
    ACTION_MAX_CHARS,
    DIGEST_MAX_CHARS,
    LANE_BANNED_PHRASES,
    PROGRESS_MAX_CHARS,
    build_daily_digest_message,
    build_lane_card,
    build_lane_message,
    build_ops_note_message,
    classify_lane_severity,
)


def _plain(html: str) -> str:
    return unescape(
        html.replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<code>", "")
        .replace("</code>", "")
        .replace("</a>", "")
    )


def _assert_lane_ok(
    msg: str,
    *,
    max_chars: int = PROGRESS_MAX_CHARS,
    must_contain: list[str] | None = None,
) -> None:
    assert msg.strip()
    assert len(msg) <= max_chars, f"too long ({len(msg)}): {msg!r}"
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
            "wall_seconds": 270,
        },
    )
    assert msg == (
        "<b>Download MSTC</b>\n"
        "28 OK · 1 failed · 97% ok · 6.2/min\n"
        "Still need files: 1,820 · Ready to process: 140 · Live on site: 375"
    )
    _assert_lane_ok(msg, must_contain=["Download MSTC", "28 OK", "Still need files"])


def test_download_typical_mstc_wave_is_progress_with_numbers():
    """Portal 500 noise (~15–25 fails / 150) must not hide behind Needs attention."""
    stats = {
        "downloaded": 129,
        "failed": 21,
        "still_need_files": 1130,
        "wall_seconds": 3760,
        "status": "success",
    }
    assert classify_lane_severity("download_mstc", "finished", stats) == "progress"
    msg = build_lane_message("download_mstc", "finished", stats)
    assert "Needs attention" not in msg
    assert "129 OK" in msg
    assert "21 failed" in msg
    assert "86% ok" in msg
    assert "Still need files: 1,130" in msg


def test_download_majority_fail_is_action_but_shows_numbers():
    stats = {
        "downloaded": 40,
        "failed": 110,
        "still_need_files": 900,
        "wall_seconds": 3600,
        "status": "success",
        "outcome": "wave finished with majority fails",
        "github_run_url": "https://github.com/x/y/actions/runs/9",
    }
    assert classify_lane_severity("download_mstc", "finished", stats) == "action"
    msg = build_lane_message("download_mstc", "finished", stats)
    assert "40 OK" in msg
    assert "110 failed" in msg
    assert "Needs attention" in msg
    assert "Open run" in msg


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
    assert "<b>Process catalogues</b>" in msg
    _assert_lane_ok(
        msg,
        must_contain=["Process catalogues", "+67", "Ready to process", "Ready for site", "Live:"],
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
    assert msg.startswith("<b>Update site</b>")
    _assert_lane_ok(
        msg,
        must_contain=["Update site", "Live on site: 375", "closing already passed", "expected"],
    )


def test_failed_has_open_run():
    msg = build_lane_message(
        "build_deploy",
        "failed",
        {
            "error": "count floor not met",
            "outcome": "promote refused",
            "github_run_url": "https://github.com/x/y/actions/runs/1",
        },
    )
    _assert_lane_ok(
        msg,
        max_chars=ACTION_MAX_CHARS,
        must_contain=["FAILED", "promote refused", "Open run", "count floor"],
    )
    assert "Open log" not in msg


def test_discover_minimal():
    msg = build_lane_message(
        "discover_mstc",
        "finished",
        {
            "listed": 2192,
            "new": 480,
            "queued_download": 500,
            "still_need_files": 1820,
            "ready_to_process": 140,
        },
    )
    assert msg == (
        "<b>Discover MSTC</b>\n"
        "Found 2,192 live · 480 new · 500 queued\n"
        "Still need files: 1,820 · Ready to process: 140"
    )


def test_action_retries_exhausted():
    msg = build_lane_card(
        "download_mstc",
        "action",
        {
            "outcome": "automatic retries used up",
            "context": "Next scheduled run will try again",
            "github_run_url": "https://github.com/x/y/actions/runs/9",
        },
    )
    _assert_lane_ok(
        msg,
        max_chars=ACTION_MAX_CHARS,
        must_contain=["Needs attention", "retries used up", "Open run"],
    )


def test_critical_deploy_failed():
    msg = build_lane_card(
        "build_deploy",
        "critical",
        {
            "outcome": "promote refused",
            "error": "count floor not met",
            "github_run_url": "https://github.com/x/y/actions/runs/2",
        },
    )
    assert "<b>FAILED</b> — promote refused" in msg
    assert "<code>count floor not met</code>" in msg


def test_daily_digest_golden():
    msg = build_daily_digest_message(
        {
            "when": "20 Jul · 09:00 IST",
            "live_on_site": 375,
            "ready_for_site": 40,
            "still_need_files": 120,
            "downloaded_yesterday": 180,
            "processed_yesterday": 160,
            "failed_yesterday": 3,
            "all_clear": False,
            "note": "3 failures yesterday — check Download MSTC",
        }
    )
    assert msg.startswith("<b>Daily catalogue</b>")
    assert "Live on site: 375" in msg
    assert "Yesterday:" in msg
    assert len(msg) <= DIGEST_MAX_CHARS


def test_zero_delta_is_silent():
    assert classify_lane_severity("download_mstc", "finished", {"downloaded": 0, "failed": 0}) == "silent"
    assert (
        classify_lane_severity("discover_mstc", "finished", {"listed": 2000, "new": 0, "queued": 0})
        == "silent"
    )
    assert classify_lane_severity("parse", "finished", {"parsed": 0, "failed": 0}) == "silent"
    assert classify_lane_severity("publish_media", "finished", {"ok_count": 0, "fail_count": 0}) == "silent"


def test_ops_note_typography():
    msg = build_ops_note_message("Inbox", "Acked Deep instructions", bullets=["restart download", "check R2"])
    assert msg.startswith("<b>Inbox</b>")
    assert "· restart download" in msg


def test_html_escape_dynamic_error():
    msg = build_lane_card(
        "download_gem",
        "action",
        {"outcome": "stalled", "error": "bad <tag> & boom"},
    )
    assert "bad &lt;tag&gt; &amp; boom" in msg
