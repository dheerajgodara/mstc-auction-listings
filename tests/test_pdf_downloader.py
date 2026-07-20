from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scraper.pdf_downloader import (
    MIN_PDF_BYTES,
    ensure_catalogue_pdf,
    is_valid_pdf_bytes,
    validate_pdf_file,
)


def _fake_pdf_bytes(size: int = MIN_PDF_BYTES + 50) -> bytes:
    body = b"%PDF-1.4\n" + (b"x" * max(0, size - 9))
    return body[:size] if size < len(body) else body + (b"y" * (size - len(body)))


def test_is_valid_pdf_bytes_rejects_html_and_tiny():
    assert is_valid_pdf_bytes(b"<html>nope</html>") is False
    assert is_valid_pdf_bytes(b"%PDF" + b"x" * 10) is False
    assert is_valid_pdf_bytes(_fake_pdf_bytes()) is True


def test_validate_pdf_file_rejects_missing_corrupt_and_tiny(tmp_path: Path):
    missing = tmp_path / "missing.pdf"
    assert validate_pdf_file(missing) is False

    tiny = tmp_path / "tiny.pdf"
    tiny.write_bytes(b"%PDF-1.4\n")
    assert validate_pdf_file(tiny) is False

    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"<html>" + (b"x" * MIN_PDF_BYTES))
    assert validate_pdf_file(corrupt) is False

    good = tmp_path / "good.pdf"
    good.write_bytes(_fake_pdf_bytes())
    assert validate_pdf_file(good) is True


def test_ensure_catalogue_pdf_cache_hit(tmp_path: Path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    cached = pdf_dir / "123.pdf"
    cached.write_bytes(_fake_pdf_bytes())

    with patch("scraper.pdf_downloader.download_pdf") as download:
        path, downloaded = ensure_catalogue_pdf("123", pdf_dir)
    assert path == cached
    assert downloaded is False
    download.assert_not_called()


def test_ensure_catalogue_pdf_replaces_corrupt_cache(tmp_path: Path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    corrupt = pdf_dir / "456.pdf"
    corrupt.write_bytes(b"<html>not a pdf</html>" + (b"x" * MIN_PDF_BYTES))

    def _write_good(auction_id: str, output_path: Path) -> Path:
        output_path.write_bytes(_fake_pdf_bytes())
        return output_path

    with patch("scraper.pdf_downloader.download_pdf", side_effect=_write_good) as download:
        path, downloaded = ensure_catalogue_pdf("456", pdf_dir)

    assert downloaded is True
    assert path == pdf_dir / "456.pdf"
    assert validate_pdf_file(path)
    download.assert_called_once()


def test_ensure_catalogue_pdf_raises_when_download_invalid(tmp_path: Path):
    pdf_dir = tmp_path / "pdfs"

    def _write_html(auction_id: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"<html>" + (b"x" * MIN_PDF_BYTES))
        return output_path

    with patch("scraper.pdf_downloader.download_pdf", side_effect=_write_html):
        with pytest.raises(ValueError, match="PDF validation failed"):
            ensure_catalogue_pdf("789", pdf_dir)


def test_download_pdf_retries_on_500_then_succeeds(tmp_path: Path):
    import requests
    from scraper.pdf_downloader import download_pdf

    good = _fake_pdf_bytes()
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status, content, url="https://mstc/example"):
            self.status_code = status
            self.content = content
            self.url = url
            self.headers = {
                "Content-Type": "application/pdf" if content[:4] == b"%PDF" else "text/html"
            }

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code}", response=self)

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResp(500, b"\r\n<html>Error 500</html>")
        return FakeResp(200, good)

    out = tmp_path / "999.pdf"
    with patch("scraper.pdf_downloader.time.sleep"):
        with patch("requests.Session") as Sess:
            inst = Sess.return_value
            inst.post.side_effect = fake_post
            path = download_pdf(
                "999", out, retries=5, backoff_base_sec=0.01, backoff_cap_sec=0.05
            )

    assert path == out
    assert validate_pdf_file(out)
    assert calls["n"] == 3

