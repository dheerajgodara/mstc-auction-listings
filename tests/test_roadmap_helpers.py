"""Roadmap helper tests: reports, notify, status metrics."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.notify import send_failure_notification
from scraper.refresh_reports import render_final_report_md
from scraper.telegram_reporter import build_telegram_message, send_telegram_message


def test_final_report_shows_deploy_false_on_dry_run():
    payload = {
        "run_id": "run_test",
        "status": "success",
        "deploy_requested": False,
        "deploy": {"deployed": False, "skipped": True},
        "total_auctions": 1816,
        "total_lots": 12200,
        "by_source": {"mstc": 1681, "gem_forward": 74, "eauction": 61},
    }
    md = render_final_report_md(payload)
    assert "**Deployed:** False" in md


def test_final_report_includes_too_small_document_recovery():
    payload = {
        "run_id": "run_test",
        "status": "success",
        "deploy": {"deployed": False, "skipped": True},
        "document_recovery": {
            "failed_total": 42,
            "too_small": 17,
            "failed_by_reason": {"too_small": 17, "http_error": 25},
            "failed_by_doc_type": {"annexure": 12, "photo": 5},
        },
    }
    md = render_final_report_md(payload)
    assert "Document recovery" in md
    assert "too_small" in md
    assert "17" in md
    assert "do not fail auction extraction" in md


def test_send_failure_notification_skips_without_url(monkeypatch):
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    assert send_failure_notification(summary="test failure") is False


def test_send_failure_notification_posts_when_configured(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.com/hook")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("scraper.notify.urllib.request.urlopen", return_value=mock_resp) as urlopen:
        ok = send_failure_notification(summary="pipeline failed", payload={"run_id": "x"})

    assert ok is True
    urlopen.assert_called_once()


def test_telegram_message_includes_operational_counts():
    message = build_telegram_message(
        {
            "run_id": "run_1",
            "status": "success",
            "started_at": "2026-07-10T02:00:00+05:30",
            "finished_at": "2026-07-10T02:30:00+05:30",
            "total_auctions": 1816,
            "total_lots": 12200,
            "by_source": {"mstc": 1681, "eauction": 61, "gem_forward": 74},
            "safety_gates": {"passed": True},
            "deploy": {"deployed": True},
        },
        event="success",
    )
    assert "run_1" in message
    assert "Auctions: 1816" in message
    assert "eauction=61" in message
    assert "Deploy: yes" in message


def test_telegram_comparison_message_includes_queue_and_decisions():
    message = build_telegram_message(
        {
            "run_id": "run_2",
            "status": "running",
            "started_at": "2026-07-10T02:00:00+05:30",
            "min_closing_date": "2026-07-11",
            "mode": "incremental_queue",
            "max_deep_scrape_per_run": 200,
            "discovery": {
                "duration_sec": 31.2,
                "count": 1860,
                "by_source": {"mstc": 1700, "gem_forward": 90, "eauction": 70},
            },
            "incremental_work_plan": {
                "full_counts": {
                    "new": 120,
                    "changed": 40,
                    "needs_repair": 10,
                    "unchanged": 1690,
                    "removed": 5,
                },
                "selected_action_counts": {"deep_parse": 200, "reuse_discovery": 20},
                "full_action_counts": {"deep_parse": 220, "reuse_previous": 1690},
                "queue": {
                    "selected_count": 200,
                    "pending_after_selection": 20,
                    "estimated_runs_to_clear": 1,
                },
            },
        },
        event="comparison_done",
    )
    assert "comparison complete" in message
    assert "Discovery: total=1860" in message
    assert "new=120 changed=40 repair=10 same=1690 removed=5" in message
    assert "selected_deep=200 / full_deep=220" in message
    assert "Queue: selected=200 pending=20 eta_runs=1" in message


def test_telegram_deep_scrape_message_includes_runtime_and_failures():
    message = build_telegram_message(
        {
            "run_id": "run_3",
            "status": "running",
            "started_at": "2026-07-10T02:00:00+05:30",
            "batch_scrape": {
                "duration_sec": 367.4,
                "manifest_summary": {"done": 198, "failed": 2, "total": 200},
                "docs_budget_remaining": 1400,
                "failed_batches": ["mstc:123", "gem_forward:456"],
            },
        },
        event="deep_scrape_done",
    )
    assert "deep scrape complete" in message
    assert "done=198 failed=2 total=200 runtime=6m 7s" in message
    assert "Docs budget left: 1400" in message
    assert "Failed batches: mstc:123, gem_forward:456" in message


def test_send_telegram_message_skips_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_telegram_message("hello") is False


def test_status_report_local_build_metrics(tmp_path: Path):
    repo = tmp_path
    out_dir = repo / "web" / "out"
    out_dir.mkdir(parents=True)
    index = out_dir / "index.html"
    index.write_text("<html><body>shell</body></html>", encoding="utf-8")
    data_dir = out_dir / "data"
    data_dir.mkdir()
    (data_dir / "auctions-data.js").write_text("window.__AUCTIONS_EXPORT__ = {};", encoding="utf-8")

    from scraper.status_report import build_status_report

    report = build_status_report(repo_root=repo, check_live=False)
    assert report["local_build"]["local_build_present"] is True
    assert report["local_build"]["index_html_bytes"] == index.stat().st_size
    assert report["local_build"]["auctions_data_js_bytes"] > 0
