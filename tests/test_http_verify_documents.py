"""http_verify samples lot.documents cached/thumbnail URLs."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.http_verify import _pick_sample_urls


def test_pick_sample_urls_includes_lot_documents(tmp_path: Path):
    public = tmp_path
    doc = public / "docs" / "589631" / "Photo.pdf"
    thumb = public / "thumbs" / "589631" / "120.0" / "Photo.webp"
    doc.parent.mkdir(parents=True)
    thumb.parent.mkdir(parents=True)
    doc.write_bytes(b"%PDF")
    thumb.write_bytes(b"WEBP")

    export = {
        "auctions": [
            {
                "id": "589631",
                "source": "mstc",
                "pdf_url": None,
                "lots": [
                    {
                        "preview_images": [],
                        "documents": [
                            {
                                "type": "photo",
                                "filename": "Photo.pdf",
                                "cached_url": "docs/589631/Photo.pdf",
                                "thumbnail_url": "thumbs/589631/120.0/Photo.webp",
                                "status": "thumbnail_ready",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    candidate = tmp_path / "auctions.json"
    candidate.write_text(json.dumps(export), encoding="utf-8")

    pdf_rel, thumb_rel, skipped = _pick_sample_urls(
        candidate, output_assets_dir=public
    )
    assert pdf_rel == "docs/589631/Photo.pdf"
    assert thumb_rel == "thumbs/589631/120.0/Photo.webp"
    assert skipped == []


def test_pick_sample_urls_skips_missing_lot_documents(tmp_path: Path):
    export = {
        "auctions": [
            {
                "id": "589631",
                "source": "mstc",
                "lots": [
                    {
                        "documents": [
                            {
                                "cached_url": "docs/589631/missing.pdf",
                                "thumbnail_url": "thumbs/589631/1/missing.webp",
                                "status": "thumbnail_ready",
                                "filename": "missing.pdf",
                                "type": "photo",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    candidate = tmp_path / "auctions.json"
    candidate.write_text(json.dumps(export), encoding="utf-8")
    pdf_rel, thumb_rel, skipped = _pick_sample_urls(
        candidate, output_assets_dir=tmp_path
    )
    assert pdf_rel is None
    assert thumb_rel is None
    assert any("docs/589631/missing.pdf" in s for s in skipped)
