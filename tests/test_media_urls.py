"""Unit tests for CDN media URL absolutization."""

from __future__ import annotations

from scraper.media_urls import absolutize_auction_media, absolutize_media_url
from scraper.object_store import media_key_from_url


def test_absolutize_relative_pdf(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://files.csmg.in")
    # config already imported — absolutize uses public_object_url which reads config module attrs
    from scraper import config

    monkeypatch.setattr(config, "R2_PUBLIC_BASE_URL", "https://files.csmg.in")
    from scraper import media_urls

    monkeypatch.setattr(media_urls, "R2_PUBLIC_BASE_URL", "https://files.csmg.in")
    assert absolutize_media_url("pdfs/1.pdf") == "https://files.csmg.in/pdfs/1.pdf"


def test_media_key_from_legacy_hostinger():
    assert media_key_from_url("https://scrapauctionindia.com/auctions/pdfs/1.pdf") == "pdfs/1.pdf"
    assert media_key_from_url("thumbs/a/1.webp") == "thumbs/a/1.webp"


def test_absolutize_auction_nested(monkeypatch):
    from scraper import config, media_urls, object_store

    monkeypatch.setattr(config, "R2_PUBLIC_BASE_URL", "https://files.csmg.in")
    monkeypatch.setattr(media_urls, "R2_PUBLIC_BASE_URL", "https://files.csmg.in")
    monkeypatch.setattr(object_store, "R2_PUBLIC_BASE_URL", "https://files.csmg.in")
    rec = {
        "pdf_url": "pdfs/9.pdf",
        "lots": [
            {
                "documents": [
                    {
                        "cached_url": "docs/9/a.pdf",
                        "thumbnail_url": "thumbs/9/a.webp",
                    }
                ]
            }
        ],
    }
    absolutize_auction_media(rec)
    assert rec["pdf_url"].startswith("https://files.csmg.in/")
    assert rec["lots"][0]["documents"][0]["cached_url"].startswith(
        "https://files.csmg.in/docs/"
    )
    assert rec["lots"][0]["documents"][0]["thumbnail_url"].startswith(
        "https://files.csmg.in/thumbs/"
    )
