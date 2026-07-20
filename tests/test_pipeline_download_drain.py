from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.pipeline_download import run_pipeline_download
from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger


def test_download_drain_exits_when_backlog_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "0")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    # All done with media synced — nothing to download.
    now = "2026-07-18T00:00:00+05:30"
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="pending",
            pdf_path="pdfs/1.pdf",
            media_synced=True,
            first_queued_at=now,
            updated_at=now,
        )
    )
    write_ledger(ledger, ledger_path)
    (public / "pdfs" / "1.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    with patch("scraper.pipeline_download.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_download.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_download.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch("scraper.pipeline_download.REPO_ROOT", repo):
                    with patch("scraper.pipeline_download.pull_ledger", return_value=True):
                        with patch("scraper.pipeline_download.push_ledger", return_value=True):
                            with patch("scraper.pipeline_download.push_raw_store") as _:
                                with patch(
                                    "scraper.pipeline_download.push_public_media"
                                ) as push_media:
                                    from scraper.raw_store import RawSyncResult

                                    push_media.return_value = RawSyncResult(True, True, "ok")
                                    with patch(
                                        "scraper.pipeline_download.send_telegram_report",
                                        return_value=True,
                                    ):
                                        with patch(
                                            "scraper.pipeline_download.reset_download_retry_state"
                                        ):
                                            with patch(
                                                "scraper.pipeline_download.acquire_refresh_lock"
                                            ):
                                                with patch(
                                                    "scraper.pipeline_download.release_refresh_lock"
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_download.send_lane_report",
                                                        return_value=True,
                                                    ):
                                                        result = run_pipeline_download(
                                                            repo_root=repo,
                                                            batch_size=25,
                                                            max_batches=5,
                                                            max_download=25,
                                                            skip_docs=True,
                                                        )
    assert result["status"] == "success"
    assert result["download_ok"] == 0
    assert result["ok_count"] == 0
    assert result["batches_completed"] == 0
    assert result["backlog_left"] == 0
