"""Tests for unsafe lot thumb migration / URL rewrite (rsync code-23 unfreeze)."""

from __future__ import annotations

from pathlib import Path

from scraper.document_cache import (
    migrate_unsafe_thumb_dirs,
    rewrite_thumb_lot_segment,
    safe_lot_dirname,
)
from scraper.export_hygiene import rewrite_unsafe_thumb_urls


def test_safe_lot_dirname_decimal_and_spaces() -> None:
    assert safe_lot_dirname("4.0") == "4_0"
    assert safe_lot_dirname("Lot No.30") == "Lot_No_30"
    assert safe_lot_dirname("19.") == "19"
    assert safe_lot_dirname("1") == "1"


def test_rewrite_thumb_lot_segment() -> None:
    assert (
        rewrite_thumb_lot_segment("thumbs/592237/4.0/Annex.webp")
        == "thumbs/592237/4_0/Annex.webp"
    )
    assert (
        rewrite_thumb_lot_segment("/thumbs/592237/4.0/Annex.webp")
        == "/thumbs/592237/4_0/Annex.webp"
    )
    assert rewrite_thumb_lot_segment("docs/1/a.pdf") == "docs/1/a.pdf"


def test_migrate_unsafe_thumb_dirs_renames(tmp_path: Path) -> None:
    thumbs = tmp_path / "thumbs"
    src = thumbs / "592237" / "4.0"
    src.mkdir(parents=True)
    (src / "Annex.webp").write_bytes(b"webp")
    stats = migrate_unsafe_thumb_dirs(thumbs)
    assert stats["renamed"] == 1
    dest = thumbs / "592237" / "4_0" / "Annex.webp"
    assert dest.is_file()
    assert not (thumbs / "592237" / "4.0").exists()


def test_migrate_unsafe_thumb_dirs_merges_into_existing(tmp_path: Path) -> None:
    thumbs = tmp_path / "thumbs"
    safe = thumbs / "1" / "4_0"
    unsafe = thumbs / "1" / "4.0"
    safe.mkdir(parents=True)
    unsafe.mkdir(parents=True)
    (safe / "old.webp").write_bytes(b"old")
    (unsafe / "new.webp").write_bytes(b"new")
    stats = migrate_unsafe_thumb_dirs(thumbs)
    assert stats["merged"] == 1
    assert (safe / "old.webp").is_file()
    assert (safe / "new.webp").is_file()
    assert not unsafe.exists()


def test_rewrite_unsafe_thumb_urls_in_export() -> None:
    export = {
        "auctions": [
            {
                "id": "mstc:1",
                "lots": [
                    {
                        "lot_id": "4.0",
                        "preview_images": ["thumbs/1/4.0/a.webp"],
                        "documents": [
                            {
                                "filename": "a.pdf",
                                "thumbnail_url": "thumbs/1/4.0/a.webp",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    stats = rewrite_unsafe_thumb_urls(export)
    assert stats["rewritten"] == 2
    lot = export["auctions"][0]["lots"][0]
    assert lot["preview_images"] == ["thumbs/1/4_0/a.webp"]
    assert lot["documents"][0]["thumbnail_url"] == "thumbs/1/4_0/a.webp"
