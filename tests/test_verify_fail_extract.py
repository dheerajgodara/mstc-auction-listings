"""Tests for verify-build FAIL extraction and critical Update site cards."""

from __future__ import annotations

from html import unescape

from scraper.telegram_reporter import ACTION_MAX_CHARS, build_lane_message
from scraper.verify_fail_extract import extract_fail_lines, summarize_command_failure


def _plain(html: str) -> str:
    return unescape(
        html.replace("<b>", "")
        .replace("</b>", "")
        .replace("<code>", "")
        .replace("</code>", "")
        .replace("</a>", "")
    )


OK_HEAVY_VERIFY_OUTPUT = """
OK  Rausch primary token exists
OK  launch: sitemap excludes /map/
OK  launch: sitemap excludes /watchlist/
OK  launch: sitemap excludes /saved/
OK  launch: sitemap excludes /status/
FAIL  app shell keeps marketplace source disclaimer
OK  launch: site has robots.txt
OK  launch: sitemap excludes /insights/
""" * 20 + """
FAIL  app shell keeps marketplace source disclaimer
 ELIFECYCLE  Command failed with exit code 1.
"""


def test_extract_fail_lines_prefers_fail_over_ok_noise():
    fails = extract_fail_lines(OK_HEAVY_VERIFY_OUTPUT, limit=3)
    assert fails == ["app shell keeps marketplace source disclaimer"]


def test_summarize_command_failure_short_and_actionable():
    short, fails, tail = summarize_command_failure(
        ["pnpm", "run", "verify-build"],
        returncode=1,
        stdout=OK_HEAVY_VERIFY_OUTPUT,
        stderr="",
    )
    assert fails
    assert "FAIL app shell keeps marketplace source disclaimer" in short
    assert "pnpm run verify-build" in short
    assert "OK  launch: sitemap excludes /watchlist/" not in short
    assert "FAIL" in tail or "app shell" in tail


def test_deploy_failed_telegram_shows_fail_not_ok_tail():
    short, fails, _tail = summarize_command_failure(
        ["pnpm", "run", "verify-build"],
        returncode=1,
        stdout=OK_HEAVY_VERIFY_OUTPUT,
        stderr="",
    )
    msg = build_lane_message(
        "build_deploy",
        "failed",
        {
            "outcome": "promote refused",
            "error": short,
            "github_run_url": "https://github.com/x/y/actions/runs/1",
        },
    )
    plain = _plain(msg)
    assert len(msg) <= ACTION_MAX_CHARS
    assert "FAILED" in plain
    assert "Update site" in plain
    assert "app shell keeps marketplace source disclaimer" in plain
    assert "sitemap excludes /watchlist" not in plain
    assert fails


def test_deploy_failed_telegram_uses_short_summary_from_pipeline():
    msg = build_lane_message(
        "build_deploy",
        "failed",
        {
            "error": "pnpm run verify-build: FAIL app shell keeps marketplace source disclaimer",
            "github_run_url": "https://github.com/x/y/actions/runs/2",
        },
    )
    plain = _plain(msg)
    assert "app shell keeps marketplace source disclaimer" in plain
    assert "Open run" in msg or "actions/runs/2" in msg
