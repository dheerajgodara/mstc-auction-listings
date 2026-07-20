"""Batch-end retry + inter-auction pause behavior for download lane."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.pipeline_download import run_pipeline_download
from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger


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


def test_batch_end_retries_failures_and_pauses_between_items(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "0")

    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.extend([_pending_item("10"), _pending_item("11")])
    write_ledger(ledger, ledger_path)

    calls: list[str] = []
    sleep_calls: list[float] = []

    def fake_mstc(*, item, ledger, **_kwargs):
        calls.append(str(item.source_auction_id))
        # Fail first pass for 10; succeed on retry. Always succeed 11.
        if item.source_auction_id == "10" and calls.count("10") == 1:
            from scraper.pipeline_ledger import mark_download

            mark_download(ledger, item.stable_key, ok=False, error="transient")
            return False, 0
        from scraper.pipeline_ledger import mark_download

        mark_download(
            ledger,
            item.stable_key,
            ok=True,
            hostinger_doc_path=f"pdfs/{item.source_auction_id}.pdf",
            hostinger_doc_url=f"https://example.com/pdfs/{item.source_auction_id}.pdf",
            doc_sha256="abc",
        )
        return True, 0

    with patch("scraper.pipeline_download.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_download.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_download.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch("scraper.pipeline_download.REPO_ROOT", repo):
                    with patch("scraper.pipeline_download.DOWNLOAD_BATCH_RETRY_ROUNDS", 2):
                        with patch(
                            "scraper.pipeline_download.DOWNLOAD_SUCCESS_PAUSE_SEC", 5.0
                        ):
                            with patch(
                                "scraper.pipeline_download.pull_ledger", return_value=True
                            ):
                                with patch(
                                    "scraper.pipeline_download.push_ledger", return_value=True
                                ):
                                    with patch(
                                        "scraper.pipeline_download.pull_public_pdf_files"
                                    ) as pull_pdfs:
                                        from scraper.raw_store import RawSyncResult

                                        pull_pdfs.return_value = RawSyncResult(
                                            True, True, "ok"
                                        )
                                        with patch(
                                            "scraper.pipeline_download.send_telegram_report",
                                            return_value=True,
                                        ):
                                            with patch(
                                                "scraper.pipeline_download.send_lane_report",
                                                return_value=True,
                                            ):
                                                with patch(
                                                    "scraper.pipeline_download.acquire_refresh_lock"
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_download.release_refresh_lock"
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_download._download_one_mstc",
                                                            side_effect=fake_mstc,
                                                        ):
                                                            with patch(
                                                                "scraper.pipeline_download.time.sleep",
                                                                side_effect=lambda s: sleep_calls.append(
                                                                    s
                                                                ),
                                                            ):
                                                                result = run_pipeline_download(
                                                                    repo_root=repo,
                                                                    batch_size=25,
                                                                    max_batches=1,
                                                                    max_download=10,
                                                                    skip_docs=True,
                                                                    source="mstc",
                                                                )

    assert result["status"] == "success"
    assert result["ok_count"] == 2
    assert result["fail_count"] == 0
    # First pass: 10 fail, 11 ok; batch-end retry: 10 ok.
    assert calls == ["10", "11", "10"]
    # Pause after every auction attempt (including retry).
    assert sleep_calls == [5.0, 5.0, 5.0]
    assert result["batch_reports"][0]["retry_left"] == 0
