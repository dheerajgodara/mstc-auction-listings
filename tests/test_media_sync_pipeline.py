"""Tests for parse-time media sync gating."""

from __future__ import annotations

from pathlib import Path

from scraper.media_sync import export_needs_media_push, media_push_required


def test_media_push_required_defaults_on(monkeypatch):
    monkeypatch.delenv("MEDIA_PUSH_REQUIRED", raising=False)
    assert media_push_required() is True
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "0")
    assert media_push_required() is False
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "false")
    assert media_push_required() is False


def test_export_needs_media_push_when_downloaded(tmp_path: Path):
    export = {"auctions": []}
    assert export_needs_media_push(export, public_dir=tmp_path, documents_downloaded=3)
    assert not export_needs_media_push(export, public_dir=tmp_path, documents_downloaded=0)


def test_export_needs_media_push_when_files_on_disk(tmp_path: Path):
    doc = tmp_path / "docs" / "1" / "a.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"%PDF")
    export = {
        "auctions": [
            {
                "id": "1",
                "lots": [
                    {
                        "documents": [
                            {
                                "cached_url": "docs/1/a.pdf",
                                "filename": "a.pdf",
                                "type": "photo",
                                "status": "downloaded",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    assert export_needs_media_push(export, public_dir=tmp_path, documents_downloaded=0)
