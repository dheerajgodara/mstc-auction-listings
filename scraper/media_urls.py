"""Rewrite relative media keys to absolute CDN URLs (files.scrapauctionindia.com)."""

from __future__ import annotations

from typing import Any

from scraper.config import R2_PUBLIC_BASE_URL
from scraper.object_store import media_key_from_url, public_object_url
from scraper.pipeline_ledger import public_doc_url


def absolutize_media_url(value: str | None) -> str | None:
    """Convert relative pdfs/docs/thumbs path (or legacy Hostinger URL) to CDN URL."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.startswith(R2_PUBLIC_BASE_URL.rstrip("/")):
        return raw
    key = media_key_from_url(raw)
    if key:
        return public_object_url(key) or public_doc_url(key)
    if raw.startswith(("http://", "https://")):
        # External portal URL — leave alone.
        return raw
    rel = raw.lstrip("/")
    if rel.startswith(("pdfs/", "docs/", "thumbs/")):
        return public_object_url(rel) or public_doc_url(rel)
    return raw


def absolutize_auction_media(record: dict[str, Any]) -> dict[str, Any]:
    """In-place rewrite of media fields on one auction dict; returns same dict."""
    for key in ("pdf_url", "hostinger_doc_path", "hostinger_doc_url", "object_doc_url"):
        if key in record and isinstance(record.get(key), str):
            if key == "hostinger_doc_path":
                # Keep relative key; also set absolute companions.
                rel = str(record[key]).lstrip("/")
                if rel.startswith(("pdfs/", "docs/")):
                    record["hostinger_doc_path"] = rel
                    cdn = absolutize_media_url(rel)
                    if cdn:
                        record["object_doc_url"] = cdn
                        record["hostinger_doc_url"] = cdn
                        if not record.get("pdf_url") or str(record.get("pdf_url")).startswith(
                            ("pdfs/", "docs/", "/")
                        ):
                            record["pdf_url"] = cdn
                continue
            abs_u = absolutize_media_url(str(record[key]))
            if abs_u:
                record[key] = abs_u

    if record.get("pdf_url"):
        abs_pdf = absolutize_media_url(str(record["pdf_url"]))
        if abs_pdf:
            record["pdf_url"] = abs_pdf
            record.setdefault("object_doc_url", abs_pdf)
            record["hostinger_doc_url"] = abs_pdf

    docs = record.get("document_urls")
    if isinstance(docs, list):
        record["document_urls"] = [
            absolutize_media_url(d) if isinstance(d, str) else d for d in docs
        ]

    lots = record.get("lots")
    if isinstance(lots, list):
        for lot in lots:
            if not isinstance(lot, dict):
                continue
            previews = lot.get("preview_images")
            if isinstance(previews, list):
                lot["preview_images"] = [
                    absolutize_media_url(p) if isinstance(p, str) else p for p in previews
                ]
            for doc in lot.get("documents") or []:
                if not isinstance(doc, dict):
                    continue
                for fld in ("cached_url", "thumbnail_url"):
                    if doc.get(fld):
                        abs_u = absolutize_media_url(str(doc[fld]))
                        if abs_u:
                            doc[fld] = abs_u
    return record


def absolutize_export_media(payload: dict[str, Any]) -> dict[str, Any]:
    auctions = payload.get("auctions")
    if isinstance(auctions, list):
        for a in auctions:
            if isinstance(a, dict):
                absolutize_auction_media(a)
    return payload
