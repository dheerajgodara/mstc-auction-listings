"""Tests for lot.documents asset integrity scrubbing."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.asset_integrity import (
    find_missing_assets,
    scrub_lot_documents,
)
from scraper.finalize_public_export import remove_missing_local_asset_links


def test_scrub_lot_documents_clears_missing_cached_and_thumb(tmp_path: Path):
    public = tmp_path
    (public / "docs" / "589631").mkdir(parents=True)
    # no files written — both refs missing
    lot = {
        "lot_id": "120.0",
        "documents": [
            {
                "type": "photo",
                "filename": "Photo_test.pdf",
                "cached_url": "docs/589631/Photo_test.pdf",
                "thumbnail_url": "thumbs/589631/120.0/Photo_test.webp",
                "status": "thumbnail_ready",
            }
        ],
        "preview_images": ["thumbs/589631/120.0/Photo_test.webp"],
    }
    removed = scrub_lot_documents(lot, public_dir=public)
    assert removed["docs"] >= 1
    assert removed["thumbs"] >= 1
    doc = lot["documents"][0]
    assert doc["cached_url"] is None
    assert doc["thumbnail_url"] is None
    assert doc["status"] == "pending_cache"
    assert lot["preview_images"] == []


def test_scrub_keeps_existing_files(tmp_path: Path):
    public = tmp_path
    doc_path = public / "docs" / "589631" / "Photo_test.pdf"
    thumb_path = public / "thumbs" / "589631" / "120.0" / "Photo_test.webp"
    doc_path.parent.mkdir(parents=True)
    thumb_path.parent.mkdir(parents=True)
    doc_path.write_bytes(b"%PDF-1.4 fake")
    thumb_path.write_bytes(b"RIFF....WEBP")
    lot = {
        "lot_id": "120.0",
        "documents": [
            {
                "type": "photo",
                "filename": "Photo_test.pdf",
                "cached_url": "docs/589631/Photo_test.pdf",
                "thumbnail_url": "thumbs/589631/120.0/Photo_test.webp",
                "status": "thumbnail_ready",
            }
        ],
        "preview_images": [],
    }
    removed = scrub_lot_documents(lot, public_dir=public)
    assert removed == {"docs": 0, "thumbs": 0}
    assert lot["documents"][0]["status"] == "thumbnail_ready"
    assert lot["preview_images"] == ["thumbs/589631/120.0/Photo_test.webp"]


def test_find_missing_assets_includes_lot_documents(tmp_path: Path):
    export = {
        "auctions": [
            {
                "id": "589631",
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
    missing = find_missing_assets(export, public_dir=tmp_path)
    fields = {m.field for m in missing}
    assert "documents.cached_url" in fields
    assert "documents.thumbnail_url" in fields


def test_remove_missing_local_asset_links_scrubs_lot_documents(tmp_path: Path):
    public = tmp_path
    export = {
        "auctions": [
            {
                "id": "589631",
                "pdf_url": None,
                "document_urls": [],
                "lots": [
                    {
                        "lot_id": "1",
                        "documents": [
                            {
                                "type": "photo",
                                "filename": "Photo.pdf",
                                "cached_url": "docs/589631/Photo.pdf",
                                "thumbnail_url": "thumbs/589631/1/Photo.webp",
                                "status": "thumbnail_ready",
                            }
                        ],
                        "preview_images": ["thumbs/589631/1/Photo.webp"],
                    }
                ],
            }
        ]
    }
    removed = remove_missing_local_asset_links(export, public_dir=public)
    assert removed["docs"] >= 1
    assert removed["thumbs"] >= 1
    doc = export["auctions"][0]["lots"][0]["documents"][0]
    assert doc["cached_url"] is None
    assert doc["status"] == "pending_cache"
