"""Wave-end retry behavior for fast download lane."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.pipeline_download import run_pipeline_download
from scraper.pipeline_ledger import LedgerItem, empty_ledger, load_ledger, write_ledger


def _pending_item(aid: str) -> LedgerItem:
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


def test_wave_end_retries_failures(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    monkeypatch.setenv("DOWNLOAD_FETCH_WORKERS", "1")
    monkeypatch.setenv("DOWNLOAD_BATCH_RETRY_ROUNDS", "2")

    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.extend([_pending_item("10"), _pending_item("11")])
    write_ledger(ledger, ledger_path)

    calls: list[str] = []

    def fake_fetch(*, item, **_kwargs):
        aid = str(item.source_auction_id)
        calls.append(aid)
        pdf = public / "pdfs" / f"{aid}.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 100)
        # Fail first pass for 10 only
        if aid == "10" and calls.count("10") == 1:
            return {
                "stable_key": item.stable_key,
                "source": "mstc",
                "source_auction_id": aid,
                "ok": False,
                "error": "transient",
            }
        return {
            "stable_key": item.stable_key,
            "source": "mstc",
            "source_auction_id": aid,
            "ok": True,
            "local_path": str(pdf),
            "hostinger_doc_path": f"pdfs/{aid}.pdf",
            "doc_sha256": "abc",
            "raw_html_path": None,
            "bytes": 100,
            "error": None,
        }

    def fake_flush(items, *, public_dir):
        verified = []
        for it in items:
            verified.append(
                {
                    **it,
                    "hostinger_doc_url": f"https://example.com/{it['hostinger_doc_path']}",
                }
            )
        return True, f"ok {len(verified)}", verified

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
                                        side_effect=fake_fetch,
                                    ):
                                        with patch(
                                            "scraper.pipeline_download.flush_download_files",
                                            side_effect=fake_flush,
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
                                                            run_pipeline_download(
                                                                repo_root=repo,
                                                                max_download=10,
                                                                wave_size=10,
                                                                source="mstc",
                                                            )

    by_key = load_ledger(ledger_path).by_key()
    assert by_key["mstc:10"].download == "done"
    assert by_key["mstc:11"].download == "done"
    assert calls.count("10") >= 2
