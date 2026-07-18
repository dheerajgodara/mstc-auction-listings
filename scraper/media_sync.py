"""Helpers for parse-time media push gating."""

from __future__ import annotations

import os
from pathlib import Path

from scraper.asset_integrity import export_has_new_local_media_files, find_missing_assets


def media_push_required() -> bool:
    """When true, parse must successfully push media before promoting if new docs exist."""
    raw = (os.environ.get("MEDIA_PUSH_REQUIRED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def export_needs_media_push(
    export: dict,
    *,
    public_dir: Path,
    documents_downloaded: int = 0,
) -> bool:
    """True when this parse run produced or references local docs/thumbs that should be synced."""
    if documents_downloaded > 0:
        return True
    return export_has_new_local_media_files(export, public_dir=public_dir)


def count_orphan_document_refs(export: dict, *, public_dir: Path) -> int:
    return len(
        [
            m
            for m in find_missing_assets(export, public_dir=public_dir)
            if m.field.startswith("documents.")
        ]
    )
