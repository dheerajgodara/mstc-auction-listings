"""Roadmap helper tests: reports, notify, status metrics."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.notify import send_failure_notification
from scraper.refresh_reports import render_final_report_md


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
