"""Shared helpers for local pdfs/docs/thumbs integrity in auctions.json."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

from scraper.lot_documents import update_lot_preview_images
from scraper.models import LotDocument

logger = logging.getLogger("scraper.asset_integrity")

LOCAL_ASSET_PREFIXES = ("pdfs/", "docs/", "thumbs/")
IntegrityMode = Literal["warn", "fail"]


@dataclass(frozen=True)
class MissingAssetRef:
    auction_id: str
    kind: str
    rel_path: str
    field: str


def normalize_rel(value: object) -> str:
    return str(value).lstrip("/")


def local_asset_kind(value: object) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if text.startswith(("http://", "https://")):
        return None
    text = text.lstrip("/")
    for prefix in LOCAL_ASSET_PREFIXES:
        if text.startswith(prefix):
            return prefix.rstrip("/")
    return None


def preview_url(img: object) -> str | None:
    if isinstance(img, str) and img.strip():
        return img.strip()
    if isinstance(img, dict):
        for key in ("url", "thumbnail_url", "src"):
            value = img.get(key)
            if value:
                return str(value)
    return None


def _file_exists(public_dir: Path, rel: str) -> bool:
    return (public_dir / rel).is_file()


def iter_local_asset_refs(auction: dict) -> Iterator[tuple[str, str, str]]:
    """Yield (kind, rel_path, field) for local asset refs on one auction."""
    auction_id = str(auction.get("id") or "")
    pdf_url = auction.get("pdf_url")
    kind = local_asset_kind(pdf_url)
    if kind:
        yield kind, normalize_rel(pdf_url), "pdf_url"

    for url in auction.get("document_urls") or []:
        kind = local_asset_kind(url)
        if kind:
            yield kind, normalize_rel(url), "document_urls"

    for lot in auction.get("lots") or []:
        if not isinstance(lot, dict):
            continue
        for img in lot.get("preview_images") or []:
            url = preview_url(img)
            kind = local_asset_kind(url)
            if kind and url:
                yield kind, normalize_rel(url), "preview_images"
        for doc in lot.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            cached = doc.get("cached_url")
            kind = local_asset_kind(cached)
            if kind and cached:
                yield kind, normalize_rel(cached), "documents.cached_url"
            thumb = doc.get("thumbnail_url")
            kind = local_asset_kind(thumb)
            if kind and thumb:
                yield kind, normalize_rel(thumb), "documents.thumbnail_url"
    _ = auction_id


def find_missing_assets(export: dict, *, public_dir: Path) -> list[MissingAssetRef]:
    missing: list[MissingAssetRef] = []
    for auction in export.get("auctions") or []:
        if not isinstance(auction, dict):
            continue
        auction_id = str(auction.get("id") or "")
        for kind, rel, field in iter_local_asset_refs(auction):
            if not _file_exists(public_dir, rel):
                missing.append(
                    MissingAssetRef(
                        auction_id=auction_id,
                        kind=kind,
                        rel_path=rel,
                        field=field,
                    )
                )
    return missing


def scrub_lot_documents(lot: dict, *, public_dir: Path) -> dict[str, int]:
    """Clear missing cached_url/thumbnail_url on lot.documents; rebuild preview_images.

    Returns counts by kind (docs/thumbs) of scrubbed refs.
    """
    removed = {"docs": 0, "thumbs": 0}
    documents = lot.get("documents")
    if not isinstance(documents, list):
        return removed

    scrubbed_docs: list[dict] = []
    for doc in documents:
        if not isinstance(doc, dict):
            scrubbed_docs.append(doc)
            continue
        updated = dict(doc)
        cached = updated.get("cached_url")
        if local_asset_kind(cached) is not None:
            rel = normalize_rel(cached)
            if not _file_exists(public_dir, rel):
                kind = local_asset_kind(cached) or "docs"
                removed[kind if kind in removed else "docs"] += 1
                updated["cached_url"] = None
                status = updated.get("status")
                if status in {"downloaded", "thumbnail_ready", "thumbnail_failed"}:
                    updated["status"] = "pending_cache"
                    updated["error"] = f"local asset not cached yet: {rel}"

        thumb = updated.get("thumbnail_url")
        if thumb:
            rel = None
            if local_asset_kind(thumb) is not None:
                rel = normalize_rel(thumb)
            elif str(thumb).startswith(("http://", "https://")):
                from scraper.object_store import media_key_from_url

                key = media_key_from_url(str(thumb))
                if key and key.startswith(LOCAL_ASSET_PREFIXES):
                    rel = key
            if rel and not _file_exists(public_dir, rel):
                removed["thumbs"] += 1
                updated["thumbnail_url"] = None
                if updated.get("status") == "thumbnail_ready":
                    if updated.get("cached_url"):
                        updated["status"] = "downloaded"
                    else:
                        updated["status"] = "pending_cache"
                    updated["error"] = f"local thumbnail not cached yet: {rel}"
        scrubbed_docs.append(updated)

    lot["documents"] = scrubbed_docs

    # Rebuild preview_images from remaining ready thumbs (dict → LotDocument bridge).
    model_docs: list[LotDocument] = []
    for doc in scrubbed_docs:
        if not isinstance(doc, dict):
            continue
        try:
            model_docs.append(LotDocument.model_validate(doc))
        except Exception:
            continue
    lot["preview_images"] = update_lot_preview_images(model_docs)
    return removed


def scrub_export_lot_documents(export: dict, *, public_dir: Path) -> dict[str, int]:
    """Scrub lot.documents across the export. Returns removed counts by kind."""
    removed = {"docs": 0, "thumbs": 0}
    for auction in export.get("auctions") or []:
        if not isinstance(auction, dict):
            continue
        for lot in auction.get("lots") or []:
            if not isinstance(lot, dict):
                continue
            lot_removed = scrub_lot_documents(lot, public_dir=public_dir)
            removed["docs"] += lot_removed["docs"]
            removed["thumbs"] += lot_removed["thumbs"]
            for kind, count in lot_removed.items():
                if count and kind in ("docs", "thumbs"):
                    note = f"local {kind} asset not cached yet (lot.documents scrubbed)"
                    warnings = list(auction.get("warnings") or [])
                    if note not in warnings:
                        warnings.append(note)
                    auction["warnings"] = warnings
    return removed


def auction_has_missing_document_assets(auction: dict, *, public_dir: Path) -> bool:
    for kind, rel, _field in iter_local_asset_refs(auction):
        _ = kind
        if not _file_exists(public_dir, rel):
            return True
    return False


def assert_document_integrity(
    export: dict,
    *,
    public_dir: Path,
    mode: IntegrityMode = "warn",
) -> list[MissingAssetRef]:
    missing = find_missing_assets(export, public_dir=public_dir)
    if not missing:
        return missing
    sample = "; ".join(
        f"{m.auction_id}:{m.field}:{m.rel_path}" for m in missing[:8]
    )
    msg = f"missing local assets ({len(missing)}): {sample}"
    if mode == "fail":
        raise RuntimeError(msg)
    logger.warning("%s", msg)
    return missing


def export_has_new_local_media_files(export: dict, *, public_dir: Path) -> bool:
    """True if export references at least one local docs/thumbs file that exists on disk."""
    for auction in export.get("auctions") or []:
        if not isinstance(auction, dict):
            continue
        for kind, rel, _field in iter_local_asset_refs(auction):
            if kind in {"docs", "thumbs"} and _file_exists(public_dir, rel):
                return True
    return False
