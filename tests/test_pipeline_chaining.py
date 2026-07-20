"""Event-chain kicks: download→parse and debounce when already running."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.lane_resume import kick_if_needed
from scraper.pipeline_download import run_pipeline_download
from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger


def test_kick_if_needed_skips_when_in_progress():
    with patch("scraper.lane_resume.workflow_in_progress", return_value=True):
        with patch("scraper.lane_resume.dispatch_workflow") as disp:
            ok, reason = kick_if_needed(
                "pipeline-parse-assets.yml", reason="test", backlog=10
            )
    assert ok is False
    assert reason == "already_in_progress"
    disp.assert_not_called()


def test_kick_if_needed_dispatches_when_idle():
    with patch("scraper.lane_resume.workflow_in_progress", return_value=False):
        with patch("scraper.lane_resume.dispatch_workflow", return_value=True) as disp:
            ok, reason = kick_if_needed(
                "pipeline-parse-assets.yml", reason="download_done", backlog=3
            )
    assert ok is True
    assert reason == "download_done"
    disp.assert_called_once()


def test_kick_clears_on_zero_backlog():
    with patch("scraper.lane_resume.dispatch_workflow") as disp:
        ok, reason = kick_if_needed("pipeline-parse-assets.yml", reason="x", backlog=0)
    assert ok is False
    assert reason == "backlog_clear"
    disp.assert_not_called()


def _pending(aid: str) -> LedgerItem:
    now = "2026-07-20T00:00:00+05:30"
    return LedgerItem(
        stable_key=f"mstc:{aid}",
        source="mstc",
        source_auction_id=aid,
        download="pending",
        parse="pending",
        portal_doc_url=(
            "https://www.mstcecommerce.com/auctionhome/mstc/auction_detailed_report_pdf.jsp"
        ),
        first_queued_at=now,
        updated_at=now,
    )


def test_download_kicks_parse_when_eligible(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    monkeypatch.setenv("DOWNLOAD_FETCH_WORKERS", "1")
    monkeypatch.setenv("DOWNLOAD_BATCH_RETRY_ROUNDS", "0")

    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.append(_pending("77"))
    write_ledger(ledger, ledger_path)
    pdf = public / "pdfs" / "77.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"z" * 200)

    fetch_result = {
        "stable_key": "mstc:77",
        "source": "mstc",
        "source_auction_id": "77",
        "ok": True,
        "local_path": str(pdf),
        "hostinger_doc_path": "pdfs/77.pdf",
        "doc_sha256": "abc",
        "raw_html_path": None,
        "bytes": 100,
        "error": None,
    }
    verified = [
        {**fetch_result, "hostinger_doc_url": "https://example.com/auctions/pdfs/77.pdf"}
    ]

    with patch("scraper.pipeline_download.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_download.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_download.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch("scraper.pipeline_download.REPO_ROOT", repo):
                    with patch("scraper.pipeline_download.pull_ledger", return_value=True):
                        with patch(
                            "scraper.pipeline_download.push_ledger", return_value=True
                        ):
                            with patch(
                                "scraper.pipeline_download._hostinger_ssh_config",
                                return_value={
                                    "host": "h",
                                    "port": "22",
                                    "username": "u",
                                    "key_path": "/k",
                                    "remote_dir": "/r/public_html/x",
                                },
                            ):
                                with patch(
                                    "scraper.pipeline_download.pull_public_pdf_files"
                                ):
                                    with patch(
                                        "scraper.pipeline_download.fetch_mstc_to_local",
                                        return_value=fetch_result,
                                    ):
                                        with patch(
                                            "scraper.pipeline_download.flush_download_files",
                                            return_value=(True, "ok", verified),
                                        ):
                                            with patch(
                                                "scraper.pipeline_download.acquire_refresh_lock"
                                            ):
                                                with patch(
                                                    "scraper.pipeline_download.release_refresh_lock"
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_download.send_telegram_report"
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_download.send_lane_report",
                                                            return_value=True,
                                                        ):
                                                            with patch(
                                                                "scraper.pipeline_download.publish_pipeline_status",
                                                                return_value={
                                                                    "parse_eligible": 1
                                                                },
                                                            ):
                                                                with patch(
                                                                    "scraper.pipeline_download.kick_if_needed",
                                                                    return_value=(
                                                                        True,
                                                                        "download_done_parse_eligible",
                                                                    ),
                                                                ) as kick:
                                                                    result = run_pipeline_download(
                                                                        repo_root=repo,
                                                                        max_download=5,
                                                                        wave_size=5,
                                                                        source="mstc",
                                                                    )
    assert result["ok_count"] == 1
    assert result["parse_kick"] is True
    kick.assert_called_once()
    assert kick.call_args[0][0] == "pipeline-parse-assets.yml"
