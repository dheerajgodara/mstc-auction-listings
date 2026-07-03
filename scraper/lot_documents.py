from __future__ import annotations

import re
from urllib.parse import quote

from scraper.config import MSTC_ATTACHMENT_URL
from scraper.models import LotDocument, LotDocumentType, LotRecord

FILE_EXTENSION_RE = re.compile(r"\.(pdf|jpg|jpeg|png|webp|gif)$", re.I)
STANDALONE_FILENAME_RE = re.compile(
    r"\b((?:Annex_|Photo_)[\w.-]+\.(?:pdf|jpg|jpeg|png|webp|gif))\b",
    re.I,
)
GENERIC_FILENAME_RE = re.compile(
    r"\b([\w.-]+\.(?:pdf|jpg|jpeg|png|webp|gif))\b",
    re.I,
)
ANNEXURE_LINE_RE = re.compile(
    r"Annexure for Lot\s*no\s*\d+\s*-\s*(.+?)(?=\n(?:Photo for Lot|Annexure for Lot|No document)|\Z)",
    re.I | re.S,
)
PHOTO_LINE_RE = re.compile(
    r"Photo for Lot\s*no\s*\d+\s*-\s*(.+?)(?=\n(?:Photo for Lot|Annexure for Lot|No document)|\Z)",
    re.I | re.S,
)


DOC_TYPE_BY_KIND: dict[LotDocumentType, str] = {
    "annexure": "annex",
    "photo": "photo",
    "document": "AUC_CATALOG_FILE",
    "unknown": "AUC_CATALOG_FILE",
}


def build_mstc_attachment_url(filename: str, doc_type: LotDocumentType | None = None) -> str:
    kind = doc_type or classify_document(filename)
    upper = filename.upper()
    if upper.startswith("ANNEX_"):
        kind = "annexure"
    elif upper.startswith("PHOTO_"):
        kind = "photo"
    doc_param = DOC_TYPE_BY_KIND.get(kind, "AUC_CATALOG_FILE")
    return MSTC_ATTACHMENT_URL.format(
        filename=quote(filename, safe=""),
        doc_type=doc_param,
    )


def doc_type_retry_order(filename: str) -> list[str]:
    """Return MSTC doc_type values to try, in priority order."""
    upper = filename.upper()
    if upper.startswith("PHOTO_"):
        return ["photo", "annex", "AUC_CATALOG_FILE"]
    if upper.startswith("ANNEX_"):
        return ["annex", "AUC_CATALOG_FILE"]
    if upper.startswith("STC_"):
        return ["stc", "AUC_CATALOG_FILE"]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"jpg", "jpeg", "png", "webp", "gif"}:
        return ["photo", "annex", "AUC_CATALOG_FILE"]
    if ext == "pdf":
        return ["AUC_CATALOG_FILE", "annex"]
    return ["AUC_CATALOG_FILE", "annex", "photo"]


def build_mstc_attachment_urls_with_retry(filename: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for doc_param in doc_type_retry_order(filename):
        url = MSTC_ATTACHMENT_URL.format(
            filename=quote(filename, safe=""),
            doc_type=doc_param,
        )
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def classify_document(filename: str) -> LotDocumentType:
    base = filename.strip()
    upper = base.upper()
    if upper.startswith("PHOTO_"):
        return "photo"
    if upper.startswith("ANNEX_"):
        return "annexure"
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if ext in {"jpg", "jpeg", "png", "webp", "gif"}:
        return "photo"
    if ext == "pdf":
        return "document"
    return "unknown"


def repair_wrapped_filenames(text: str) -> str:
    """Join line-wrapped PDF/image filenames from flattened catalogue text."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    lines = [ln.strip() for ln in text.split("\n")]
    merged: list[str] = []
    buffer = ""
    for line in lines:
        if not line:
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append("")
            continue
        if buffer and not FILE_EXTENSION_RE.search(buffer):
            if buffer.endswith("-") or re.search(r"[_0-9]$", buffer):
                buffer += line
            else:
                buffer += line if line.startswith(".") else line
            continue
        if buffer:
            merged.append(buffer)
        buffer = line
    if buffer:
        merged.append(buffer)
    return "\n".join(merged)


def _normalize_filename(raw: str) -> str:
    cleaned = repair_wrapped_filenames(raw).replace("\n", "").strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def _make_document(filename: str, doc_type: LotDocumentType | None = None) -> LotDocument:
    fn = _normalize_filename(filename)
    dtype = doc_type or classify_document(fn)
    return LotDocument(
        type=dtype,
        filename=fn,
        source_url=build_mstc_attachment_url(fn, dtype),
    )


def extract_document_refs(lot_documents_text: str | None) -> list[LotDocument]:
    if not lot_documents_text or not lot_documents_text.strip():
        return []
    if re.search(r"no document\s+uploaded", lot_documents_text, re.I):
        # Still parse explicit annexure/photo lines if present.
        pass

    text = repair_wrapped_filenames(lot_documents_text)
    seen: set[str] = set()
    docs: list[LotDocument] = []

    for pattern, default_type in (
        (ANNEXURE_LINE_RE, "annexure"),
        (PHOTO_LINE_RE, "photo"),
    ):
        for match in pattern.finditer(text):
            filename = _normalize_filename(match.group(1))
            if not filename or filename in seen:
                continue
            seen.add(filename)
            docs.append(_make_document(filename, default_type))

    for pattern in (STANDALONE_FILENAME_RE, GENERIC_FILENAME_RE):
        for match in pattern.finditer(text):
            filename = _normalize_filename(match.group(1))
            if not filename or filename in seen:
                continue
            seen.add(filename)
            docs.append(_make_document(filename))

    return docs


def collect_lot_document_refs(lot: LotRecord) -> list[LotDocument]:
    docs = extract_document_refs(lot.lot_documents_text)
    seen = {d.filename for d in docs}
    if lot.annexure_file:
        fn = _normalize_filename(lot.annexure_file)
        if fn and fn not in seen:
            docs.append(_make_document(fn, "annexure"))
            seen.add(fn)
    if lot.photo_file:
        fn = _normalize_filename(lot.photo_file)
        if fn and fn not in seen:
            docs.append(_make_document(fn, "photo"))
            seen.add(fn)
    return docs


def update_lot_preview_images(documents: list[LotDocument], max_images: int = 5) -> list[str]:
    previews: list[str] = []
    for doc in documents:
        if doc.thumbnail_url and doc.status == "thumbnail_ready":
            previews.append(doc.thumbnail_url)
        if len(previews) >= max_images:
            break
    return previews
