"""Extract GeM catalogue PDF/DOCX prose into listing body fields."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from scraper.text_cleanup import cleanup_ocr_text

logger = logging.getLogger(__name__)

_MAX_CHARS = 12_000
_BOILERPLATE = re.compile(
    r"(general terms and conditions|terms\s*&\s*conditions of gem|"
    r"forward auction module|disclaimer|page \d+ of \d+)",
    re.I,
)


def _extract_bytes(data: bytes) -> tuple[str, str]:
    """Return (text, quality_flag)."""
    from scraper.gem_scrap_samples_fetch import extract_pdf_text

    if data[:4] == b"%PDF" or data[:5] == b"%PDF-":
        text, ocr = extract_pdf_text(data)
        flag = "ocr" if ocr else ("text_layer" if text.strip() else "empty")
        return text, flag

    try:
        from io import BytesIO
        import zipfile

        if zipfile.is_zipfile(BytesIO(data)):
            with zipfile.ZipFile(BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    xml = zf.read("word/document.xml").decode("utf-8", "ignore")
                    text = re.sub(r"<[^>]+>", " ", xml)
                    text = re.sub(r"\s+", " ", text).strip()
                    return text, "text_layer" if text else "empty"
    except Exception as exc:
        logger.debug("docx extract failed: %s", exc)

    try:
        text = data.decode("utf-8", "ignore")
        text = re.sub(r"\s+", " ", text).strip()
        return text, "text_layer" if len(text) >= 40 else "empty"
    except Exception:
        return "", "empty"


def _clean_catalogue(text: str, *, max_chars: int = _MAX_CHARS) -> str | None:
    cleaned = cleanup_ocr_text(text) or text
    lines = []
    for line in cleaned.splitlines():
        s = line.strip()
        if not s:
            continue
        if _BOILERPLATE.search(s) and len(s) < 120:
            continue
        lines.append(s)
    joined = "\n".join(lines).strip()
    if len(joined) < 40:
        return None
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(" ", 1)[0].strip() + "…"
    return joined


def _public_dir_for(path: Path) -> Path:
    for parent in path.parents:
        if parent.name == "public":
            return parent
    return path.parent


def resolve_gem_catalogue_path(
    *,
    public_dir: Path,
    source_auction_id: str,
    hostinger_doc_path: str | None = None,
) -> Path | None:
    candidates: list[Path] = []
    if hostinger_doc_path:
        candidates.append(public_dir / hostinger_doc_path.lstrip("/"))
    aid = str(source_auction_id).strip()
    for ext in (".pdf", ".docx", ".doc"):
        candidates.append(public_dir / "docs" / "gem" / f"{aid}{ext}")
        candidates.append(public_dir / "pdfs" / "gem" / f"{aid}{ext}")
    for path in candidates:
        if path.is_file() and path.stat().st_size > 200:
            return path
    return None


def merge_gem_catalogue_into_record(
    record: dict[str, Any],
    *,
    pdf_path: Path,
    max_chars: int = _MAX_CHARS,
    make_thumb: bool = True,
) -> dict[str, Any]:
    """Mutate/return record with catalogue prose in summary, lot description, search_text."""
    try:
        raw = pdf_path.read_bytes()
    except OSError as exc:
        logger.warning("GeM catalogue read failed %s: %s", pdf_path, exc)
        return record

    text, quality = _extract_bytes(raw)
    body = _clean_catalogue(text, max_chars=max_chars)
    out = dict(record)
    warnings = list(out.get("warnings") or [])
    warnings.append(f"gem_catalogue_extract:{quality}")
    out["warnings"] = warnings

    if not body:
        if make_thumb:
            out = _maybe_attach_catalogue_thumb(out, pdf_path=pdf_path)
        return out

    summary = (out.get("item_summary") or "").strip()
    if not summary or (len(body) > len(summary) + 40 and len(summary) < 120):
        out["item_summary"] = body if len(body) <= 2000 else body[:2000].rsplit(" ", 1)[0] + "…"

    search = (out.get("search_text") or "").strip()
    if body.lower() not in search.lower():
        out["search_text"] = f"{search} {body}".strip() if search else body

    lots = list(out.get("lots") or [])
    if lots and isinstance(lots[0], dict):
        lot0 = dict(lots[0])
        existing = (lot0.get("lot_description_text") or lot0.get("item_description") or "").strip()
        if not existing or len(body) > len(existing) + 40:
            lot0["lot_description_text"] = body
            lot0["item_description"] = body
        lots[0] = lot0
        out["lots"] = lots

    if make_thumb:
        out = _maybe_attach_catalogue_thumb(out, pdf_path=pdf_path)
    return out


def _maybe_attach_catalogue_thumb(record: dict[str, Any], *, pdf_path: Path) -> dict[str, Any]:
    if pdf_path.suffix.lower() != ".pdf":
        return record
    try:
        from scraper.document_cache import safe_lot_dirname
        from scraper.thumbnails import generate_thumbnail

        aid = str(record.get("source_auction_id") or "")
        if not aid:
            return record
        lots = list(record.get("lots") or [])
        if not lots or not isinstance(lots[0], dict):
            return record
        lot0 = dict(lots[0])
        previews = list(lot0.get("preview_images") or [])
        docs = list(lot0.get("documents") or [])
        has_thumb = any(
            isinstance(d, dict) and d.get("status") == "thumbnail_ready" for d in docs
        ) or bool(previews)
        if has_thumb:
            return record

        public_dir = _public_dir_for(pdf_path)
        lot_key = safe_lot_dirname(str(lot0.get("lot_id") or "1"))
        thumb_dir = public_dir / "thumbs" / aid / lot_key
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{pdf_path.stem}.webp"
        if not generate_thumbnail(pdf_path, thumb_path) or not thumb_path.is_file():
            return record
        rel = f"thumbs/{aid}/{lot_key}/{thumb_path.name}"
        previews = list(dict.fromkeys([*previews, rel]))
        lot0["preview_images"] = previews
        docs.append(
            {
                "type": "annexure",
                "filename": pdf_path.name,
                "status": "thumbnail_ready",
                "mime_type": "application/pdf",
                "cached_url": f"docs/gem/{pdf_path.name}"
                if "docs/gem" in str(pdf_path).replace("\\", "/")
                else str(pdf_path.relative_to(public_dir)).replace("\\", "/"),
                "thumbnail_url": rel,
            }
        )
        lot0["documents"] = docs
        lots[0] = lot0
        out = dict(record)
        out["lots"] = lots
        return out
    except Exception as exc:
        logger.debug("GeM catalogue thumb skipped: %s", exc)
        return record
