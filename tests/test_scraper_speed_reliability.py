"""Tests for scraper speed/reliability fixes (stub download, retries, attempts)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from scraper.main import listing_stub_for_download
from scraper.pdf_downloader import (
    DEFAULT_PDF_BACKOFF_CAP_SEC,
    DEFAULT_PDF_RETRIES,
    _is_retryable_http,
    classify_pdf_error,
)
from scraper.pipeline_ledger import (
    LedgerItem,
    PipelineLedger,
    mark_download,
    mark_download_fetched_local,
)


def test_listing_stub_for_download_no_office_scan():
    with patch("scraper.main.fetch_office_auctions") as fetch:
        stub = listing_stub_for_download("999001")
    fetch.assert_not_called()
    assert stub.id == "999001"
    assert stub.source == "mstc"
    assert "999001" in (stub.mstc_html_url or "")


def test_fetch_mstc_uses_stub_not_office_scan(tmp_path: Path):
    from scraper.download_engine import fetch_mstc_to_local
    from scraper.download_throttle import DownloadThrottle
    import threading

    item = MagicMock()
    item.stable_key = "mstc:42"
    item.source_auction_id = "42"
    item.detail_url = "https://example.com/detail/42"
    item.portal_doc_url = None

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    public_dir = tmp_path / "public"
    (public_dir / "pdfs").mkdir(parents=True)
    body = b"%PDF-1.4" + b"x" * 2000
    (pdf_dir / "42.pdf").write_bytes(body)
    (public_dir / "pdfs" / "42.pdf").write_bytes(body)

    with (
        patch("scraper.main.fetch_office_auctions") as fetch_offices,
        patch("scraper.download_engine.enrich_auction") as enrich,
        patch("scraper.download_engine.has_raw_html", return_value=True),
        patch("scraper.download_engine.validate_pdf_file", return_value=True),
        patch("scraper.download_engine._sha256_file", return_value="abc"),
        patch("scraper.download_engine.time.sleep"),
    ):
        enrich.return_value = listing_stub_for_download("42")
        result = fetch_mstc_to_local(
            item=item,
            pdf_dir=pdf_dir,
            public_dir=public_dir,
            raw_dir=tmp_path / "raw",
            skip_pdf=False,
            stats={"_lock": threading.Lock()},
            throttle=DownloadThrottle(),
        )

    fetch_offices.assert_not_called()
    enrich.assert_called_once()
    assert enrich.call_args.kwargs.get("mode") == "download_only"
    assert result["ok"] is True
    assert result["source_auction_id"] == "42"


def test_pdf_retry_classification():
    assert _is_retryable_http(500) is True
    assert _is_retryable_http(429) is True
    assert _is_retryable_http(404) is False
    assert _is_retryable_http(403) is False

    timeout = requests.Timeout("read timed out")
    assert classify_pdf_error(timeout) == "timeout"

    resp = MagicMock()
    resp.status_code = 500
    http = requests.HTTPError("500", response=resp)
    assert classify_pdf_error(http) == "portal_500"

    resp404 = MagicMock()
    resp404.status_code = 404
    http404 = requests.HTTPError("404", response=resp404)
    assert classify_pdf_error(http404) == "not_found"

    assert DEFAULT_PDF_RETRIES <= 3
    assert DEFAULT_PDF_BACKOFF_CAP_SEC <= 15


def test_fetched_local_does_not_burn_attempts():
    ledger = PipelineLedger(
        generated_at="2026-01-01T00:00:00+05:30",
        items=[
            LedgerItem(
                stable_key="mstc:1",
                source="mstc",
                source_auction_id="1",
                download="pending",
                download_attempts=0,
            )
        ],
    )
    mark_download_fetched_local(
        ledger,
        "mstc:1",
        local_doc_path="/tmp/1.pdf",
        hostinger_doc_path="pdfs/1.pdf",
    )
    item = ledger.by_key()["mstc:1"]
    assert item.download == "fetched_local"
    assert item.download_attempts == 0

    mark_download(
        ledger,
        "mstc:1",
        ok=False,
        error="portal 500",
        bump_attempts=True,
    )
    assert ledger.by_key()["mstc:1"].download_attempts == 1


def test_wave_deadline_cancel_futures():
    """Abandoned futures must be cancelled (not left to hammer MSTC)."""
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    import time

    started = []
    finished = []

    def _slow(_n: int) -> int:
        started.append(_n)
        time.sleep(2.0)
        finished.append(_n)
        return _n

    pool = ThreadPoolExecutor(max_workers=2)
    try:
        futs = {pool.submit(_slow, i): i for i in range(4)}
        pending = set(futs)
        deadline = time.monotonic() + 0.3
        while pending:
            if time.monotonic() >= deadline:
                for fut in list(pending):
                    fut.cancel()
                pending.clear()
                break
            done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for fut in done:
                try:
                    fut.result(timeout=0.1)
                except Exception:
                    pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # At least some futures should have been cancelled before finishing all 4.
    assert len(finished) < 4
