"""Download lane soft-fails Hostinger preflight when MEDIA_R2_ONLY + R2."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.hostinger_ssh import SSH_PREFLIGHT_TIMEOUT
from scraper.pipeline_download import run_pipeline_download
from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger


def test_ssh_preflight_timeout_default_bumped() -> None:
    assert SSH_PREFLIGHT_TIMEOUT >= 25


def test_download_soft_fails_preflight_when_r2_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "0")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    now = "2026-07-18T00:00:00+05:30"
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="pending",
            pdf_path="pdfs/1.pdf",
            hostinger_doc_path="pdfs/1.pdf",
            hostinger_doc_url="https://example.com/pdfs/1.pdf",
            media_synced=True,
            first_queued_at=now,
            updated_at=now,
        )
    )
    write_ledger(ledger, ledger_path)
    (public / "pdfs" / "1.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    ssh_cfg = {
        "host": "h.example",
        "port": "22",
        "username": "u",
        "key_path": "/tmp/key",
        "remote_dir": "/remote",
    }

    with patch("scraper.pipeline_download.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_download.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_download.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch("scraper.pipeline_download.REPO_ROOT", repo):
                    with patch(
                        "scraper.pipeline_download.preflight_hostinger",
                        return_value=(False, "preflight failed (25000ms): timed out"),
                    ):
                        with patch(
                            "scraper.hostinger_ssh.hostinger_ssh_config",
                            return_value=ssh_cfg,
                        ):
                            with patch(
                                "scraper.object_store.media_r2_only",
                                return_value=True,
                            ):
                                with patch(
                                    "scraper.object_store.r2_configured",
                                    return_value=True,
                                ):
                                    with patch(
                                        "scraper.pipeline_download.pull_ledger",
                                        return_value=True,
                                    ):
                                        with patch(
                                            "scraper.pipeline_download.push_ledger",
                                            return_value=True,
                                        ):
                                            with patch(
                                                "scraper.pipeline_download.push_heartbeat",
                                                return_value=True,
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
    warnings = result.get("warnings") or []
    assert any("Hostinger preflight soft-fail" in w for w in warnings)
