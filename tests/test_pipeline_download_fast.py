"""Fast download wave: flush-then-done durability + throttle basics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.download_flush import flush_download_files
from scraper.download_throttle import HostThrottle
from scraper.pipeline_download import run_pipeline_download
from scraper.pipeline_ledger import LedgerItem, empty_ledger, load_ledger, write_ledger


def _pending_item(aid: str, *, source: str = "mstc") -> LedgerItem:
    now = "2026-07-20T00:00:00+05:30"
    portal = (
        "https://www.mstcecommerce.com/auctionhome/mstc/auction_detailed_report_pdf.jsp"
        if source == "mstc"
        else f"https://example.com/gem/{aid}.pdf"
    )
    return LedgerItem(
        stable_key=f"{source}:{aid}",
        source=source if source == "mstc" else "gem_forward",
        source_auction_id=aid,
        download="pending",
        parse="pending",
        portal_doc_url=portal,
        first_queued_at=now,
        updated_at=now,
    )


def test_flush_noop_empty():
    ok, msg, verified = flush_download_files([], public_dir=Path("/tmp"))
    assert ok
    assert verified == []


def test_circuit_opens_on_fail_streak():
    t = HostThrottle(host="x", delay_sec=0.2)
    t.outcomes.clear()
    for _ in range(10):
        t.record(ok=False, latency_sec=1.0)
    assert t.circuit_open_until > 0 or t.delay_sec > 0.2


def test_wave_flush_fail_keeps_pending(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    monkeypatch.setenv("DOWNLOAD_FETCH_WORKERS", "1")
    monkeypatch.setenv("DOWNLOAD_BATCH_RETRY_ROUNDS", "0")

    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.append(_pending_item("42"))
    write_ledger(ledger, ledger_path)

    fetch_result = {
        "stable_key": "mstc:42",
        "source": "mstc",
        "source_auction_id": "42",
        "ok": True,
        "local_path": str(public / "pdfs" / "42.pdf"),
        "hostinger_doc_path": "pdfs/42.pdf",
        "doc_sha256": "abc",
        "raw_html_path": "raw/mstc/42.html",
        "bytes": 100,
        "error": None,
    }
    (public / "pdfs" / "42.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 200)

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
                                            return_value=(False, "rsync failed", []),
                                        ):
                                            with patch(
                                                "scraper.pipeline_download.acquire_refresh_lock"
                                            ):
                                                with patch(
                                                    "scraper.pipeline_download.release_refresh_lock"
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_download.push_heartbeat",
                                                        return_value=True,
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_download.send_lane_report",
                                                            return_value=True,
                                                        ):
                                                            run_pipeline_download(
                                                                repo_root=repo,
                                                                max_download=5,
                                                                wave_size=5,
                                                                source="mstc",
                                                            )
    assert load_ledger(ledger_path).by_key()["mstc:42"].download == "fetched_local"


def test_wave_verify_success_marks_done(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    monkeypatch.setenv("DOWNLOAD_FETCH_WORKERS", "1")
    monkeypatch.setenv("DOWNLOAD_BATCH_RETRY_ROUNDS", "0")

    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.append(_pending_item("99"))
    write_ledger(ledger, ledger_path)
    (public / "pdfs" / "99.pdf").write_bytes(b"%PDF-1.4\n" + b"y" * 200)

    fetch_result = {
        "stable_key": "mstc:99",
        "source": "mstc",
        "source_auction_id": "99",
        "ok": True,
        "local_path": str(public / "pdfs" / "99.pdf"),
        "hostinger_doc_path": "pdfs/99.pdf",
        "doc_sha256": "def",
        "raw_html_path": None,
        "bytes": 100,
        "error": None,
    }
    verified = [
        {
            **fetch_result,
            "hostinger_doc_url": "https://example.com/auctions/pdfs/99.pdf",
        }
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
                                                        "scraper.pipeline_download.push_heartbeat",
                                                        return_value=True,
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_download.send_lane_report",
                                                            return_value=True,
                                                        ):
                                                            run_pipeline_download(
                                                                repo_root=repo,
                                                                max_download=5,
                                                                wave_size=5,
                                                                source="mstc",
                                                            )
    item = load_ledger(ledger_path).by_key()["mstc:99"]
    assert item.download == "done"
    assert item.hostinger_doc_path == "pdfs/99.pdf"
