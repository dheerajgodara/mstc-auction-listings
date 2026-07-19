from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import requests

from scraper.config import REQUEST_TIMEOUT, USER_AGENT
from scraper.lot_documents import (
    build_mstc_attachment_urls_with_retry,
    collect_lot_document_refs,
    update_lot_preview_images,
)
from scraper.models import AuctionRecord, LotDocument, LotRecord
from scraper.thumbnails import generate_thumbnail, get_pdf_page_count

logger = logging.getLogger(__name__)

MIN_DOC_BYTES = 500
DOC_DOWNLOAD_DELAY_SEC = 0.35


def safe_thumb_filename(filename: str) -> str:
    stem = Path(filename).stem
    safe = re.sub(r"[^\w.-]+", "_", stem).strip("._")
    return (safe or "document")[:120]


def safe_lot_dirname(lot_id: str) -> str:
    """Filesystem-safe lot folder name (avoids Hostinger rsync failures on '4.0' etc.)."""
    raw = (lot_id or "").strip() or "lot"
    safe = re.sub(r"[^\w-]+", "_", raw).strip("._")
    return (safe or "lot")[:80]


def detect_mime_type(content: bytes, filename: str, header: str | None) -> str | None:
    if header:
        return header.split(";")[0].strip().lower() or None
    if content[:4] == b"%PDF":
        return "application/pdf"
    ext = Path(filename).suffix.lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }
    return mapping.get(ext)


def _looks_like_document(content: bytes, filename: str) -> bool:
    if content[:4] == b"%PDF":
        return True
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg"} and content[:3] == b"\xff\xd8\xff":
        return True
    if ext == ".png" and content[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if ext == ".webp" and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return True
    if ext == ".gif" and content[:6] in {b"GIF87a", b"GIF89a"}:
        return True
    return False


def classify_failure_reason(error: str | None) -> str:
    if not error:
        return "unknown"
    lower = error.lower()
    if lower.startswith("http"):
        return "http_error"
    if "too small" in lower:
        return "too_small"
    if "not a valid document" in lower:
        return "invalid_content"
    if "max-docs-per-run" in lower:
        return "budget_exhausted"
    if "missing source_url" in lower:
        return "missing_url"
    return "other"


def _download_document(
    urls: list[str],
    dest: Path,
    session: requests.Session,
) -> tuple[bool, str | None, str | None, str | None]:
    last_error: str | None = None
    for url in urls:
        try:
            resp = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://www.mstcindia.co.in/",
                    "Accept": "*/*",
                },
            )
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue
            if len(resp.content) <= MIN_DOC_BYTES:
                last_error = f"file too small ({len(resp.content)} bytes)"
                continue
            if not _looks_like_document(resp.content, dest.name):
                last_error = "response is not a valid document file"
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            mime = detect_mime_type(resp.content, dest.name, resp.headers.get("Content-Type"))
            return True, mime, None, url
        except Exception as exc:
            last_error = str(exc)
    return False, None, last_error, None


def cache_lot_documents(
    auction_id: str,
    lot_id: str,
    documents: list[LotDocument],
    output_docs_dir: Path,
    output_thumbs_dir: Path,
    session: requests.Session | None = None,
) -> list[LotDocument]:
    sess = session or requests.Session()
    cached_docs: list[LotDocument] = []
    auction_docs_dir = output_docs_dir / auction_id
    lot_dir = safe_lot_dirname(lot_id)
    lot_thumbs_dir = output_thumbs_dir / auction_id / lot_dir

    for doc in documents:
        updated = doc.model_copy()
        dest = auction_docs_dir / doc.filename
        rel_cached = f"docs/{auction_id}/{doc.filename}"

        if dest.is_file() and dest.stat().st_size > MIN_DOC_BYTES:
            updated.status = "downloaded"
            updated.cached_url = rel_cached
            if not updated.mime_type:
                updated.mime_type = detect_mime_type(dest.read_bytes()[:16], doc.filename, None)
        else:
            urls = [doc.source_url] if doc.source_url else []
            if not urls:
                urls = build_mstc_attachment_urls_with_retry(doc.filename)
            elif len(urls) == 1:
                urls = build_mstc_attachment_urls_with_retry(doc.filename)
            ok, mime, err, used_url = _download_document(urls, dest, sess)
            time.sleep(DOC_DOWNLOAD_DELAY_SEC)
            if not ok:
                updated.status = "failed"
                updated.error = err
                cached_docs.append(updated)
                continue
            if used_url and used_url != doc.source_url:
                updated.source_url = used_url
            updated.status = "downloaded"
            updated.cached_url = rel_cached
            updated.mime_type = mime

        if updated.mime_type == "application/pdf" or dest.suffix.lower() == ".pdf":
            updated.page_count = get_pdf_page_count(dest)

        thumb_name = f"{safe_thumb_filename(doc.filename)}.webp"
        thumb_path = lot_thumbs_dir / thumb_name
        rel_thumb = f"thumbs/{auction_id}/{lot_dir}/{thumb_name}"

        if thumb_path.is_file() and thumb_path.stat().st_size > 0:
            updated.thumbnail_url = rel_thumb
            updated.status = "thumbnail_ready"
        elif generate_thumbnail(dest, thumb_path):
            if thumb_path.is_file() and thumb_path.stat().st_size > 0:
                updated.thumbnail_url = rel_thumb
                updated.status = "thumbnail_ready"
            else:
                updated.status = "thumbnail_failed"
                updated.error = "thumbnail file empty"
        else:
            if updated.status == "downloaded":
                updated.status = "thumbnail_failed"
                updated.error = "thumbnail generation unavailable"

        cached_docs.append(updated)

    return cached_docs


def attach_documents_to_lot(lot: LotRecord) -> LotRecord:
    docs = collect_lot_document_refs(lot)
    return lot.model_copy(
        update={
            "documents": docs,
            "preview_images": update_lot_preview_images(docs),
        }
    )


def process_auction_documents(
    record: AuctionRecord,
    *,
    docs_dir: Path,
    thumbs_dir: Path,
    skip_docs: bool,
    max_docs_remaining: int,
    session: requests.Session | None,
    stats: dict,
) -> tuple[AuctionRecord, int]:
    """Attach and optionally cache lot documents. Returns updated record and remaining budget."""
    lots: list[LotRecord] = []
    remaining = max_docs_remaining

    for lot in record.lots:
        lot_with_refs = attach_documents_to_lot(lot)
        doc_stats = stats.get("documents")
        if not isinstance(doc_stats, dict) or "refs_found" not in doc_stats:
            doc_stats = {
                "refs_found": 0,
                "attempted": 0,
                "downloaded": 0,
                "cache_hits": 0,
                "thumbnails_ready": 0,
                "failed": 0,
                "skipped_due_limit": 0,
                "failed_by_reason": {},
                "failed_by_doc_type": {},
            }
            stats["documents"] = doc_stats
        doc_stats["refs_found"] += len(lot_with_refs.documents)

        if skip_docs or not lot_with_refs.documents:
            lots.append(lot_with_refs)
            continue

        processed_docs: list[LotDocument] = []
        for doc in lot_with_refs.documents:
            dest = docs_dir / record.id / doc.filename
            already_cached = dest.is_file() and dest.stat().st_size > MIN_DOC_BYTES
            if remaining <= 0 and not already_cached:
                skipped = doc.model_copy(update={"status": "skipped", "error": "max-docs-per-run"})
                processed_docs.append(skipped)
                doc_stats["skipped_due_limit"] += 1
                continue

            before_exists = already_cached
            if not before_exists:
                doc_stats["attempted"] += 1
            cached = cache_lot_documents(
                record.id,
                lot_with_refs.lot_id,
                [doc],
                docs_dir,
                thumbs_dir,
                session=session,
            )[0]
            if not before_exists:
                remaining -= 1

            if cached.status in {"downloaded", "thumbnail_ready", "thumbnail_failed"}:
                if before_exists and cached.cached_url:
                    doc_stats["cache_hits"] += 1
                elif cached.cached_url:
                    doc_stats["downloaded"] += 1
            if cached.status == "thumbnail_ready":
                doc_stats["thumbnails_ready"] += 1
            elif cached.status in {"failed", "thumbnail_failed"}:
                doc_stats["failed"] += 1
                reason = classify_failure_reason(cached.error)
                doc_stats["failed_by_reason"][reason] = (
                    doc_stats["failed_by_reason"].get(reason, 0) + 1
                )
                doc_stats["failed_by_doc_type"][doc.type] = (
                    doc_stats["failed_by_doc_type"].get(doc.type, 0) + 1
                )

            processed_docs.append(cached)

        preview_images = update_lot_preview_images(processed_docs)
        lots.append(
            lot_with_refs.model_copy(
                update={"documents": processed_docs, "preview_images": preview_images}
            )
        )

    return record.model_copy(update={"lots": lots}), remaining
