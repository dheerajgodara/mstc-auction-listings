"""Fail-closed validation for GeM Forward auction documents.

Never treat HTML shells (Download Document / Session Expired) as catalogues.
"""

from __future__ import annotations

import re
from typing import Literal

GemDocKind = Literal["pdf", "docx", "doc", "zip"]

MIN_GEM_DOC_BYTES = 500
_UTF8_BOM = b"\xef\xbb\xbf"
_OLE_MAGIC = bytes.fromhex("d0cf11e0")
_HTML_TITLE_RE = re.compile(
    rb"<title[^>]*>\s*(Session Expired|Download Document|Enable JavaScript|Security Violation)",
    re.I,
)
_HTML_MARKERS = (
    b"<!doctype",
    b"<html",
    b"<?xml",
    b"<!--",
    b"<head",
    b"<script",
    b"<meta",
    b"<body",
)
_SHELL_MARKERS = (
    b"session-expired",
    b"file-list/",
    b"download document",
    b"before-login",
    b"x-login",
)


def _strip_bom(body: bytes) -> bytes:
    if body.startswith(_UTF8_BOM):
        return body[len(_UTF8_BOM) :]
    return body


def looks_like_gem_html_shell(body: bytes) -> bool:
    """True when bytes look like an HTML page / GeM UI shell, not a document."""
    if not body:
        return True
    head = _strip_bom(body)[:4096].lstrip().lower()
    if any(head.startswith(m) for m in _HTML_MARKERS):
        return True
    if _HTML_TITLE_RE.search(_strip_bom(body)[:8192]):
        return True
    # Mid-head HTML without classic prefix (framework shells)
    sample = head[:2048]
    if b"<html" in sample or b"<!doctype" in sample:
        return True
    # GeM shell page with file-list JS but no document magic
    if any(m in head for m in _SHELL_MARKERS) and not (
        body.startswith(b"%PDF") or body[:2] == b"PK" or body[:4] == _OLE_MAGIC
    ):
        # Only if it also looks textual/HTML-ish
        if b"<" in head[:200] and b">" in head[:400]:
            return True
    return False


def is_gem_document_bytes(
    body: bytes,
    *,
    min_bytes: int = MIN_GEM_DOC_BYTES,
) -> tuple[bool, GemDocKind | None, str | None]:
    """Return (ok, kind, error). Fail closed on HTML / unknown magic."""
    if not body or len(body) < min_bytes:
        return False, None, f"gem_doc_too_small ({len(body) if body else 0} bytes)"
    if looks_like_gem_html_shell(body):
        if b"session expired" in body[:8192].lower() or b"session-expired" in body[:8192].lower():
            return False, None, "gem_session_expired"
        if b"download document" in body[:8192].lower() or b"file-list/" in body[:4096].lower():
            return False, None, "gem_html_shell"
        return False, None, "gem_html_rejected"
    if body.startswith(b"%PDF"):
        return True, "pdf", None
    if body[:2] == b"PK":
        # ZIP container — treat as office/zip catalogue attachment
        return True, "docx", None
    if body[:4] == _OLE_MAGIC:
        return True, "doc", None
    return False, None, "gem_unknown_magic"


def extension_for_kind(kind: GemDocKind | None) -> str:
    if kind == "pdf":
        return "pdf"
    if kind == "docx":
        return "docx"
    if kind == "doc":
        return "doc"
    if kind == "zip":
        return "zip"
    return "bin"


def classify_local_gem_file(path) -> tuple[bool, GemDocKind | None, str | None]:
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return False, None, "missing_file"
    try:
        body = p.read_bytes()
    except OSError as exc:
        return False, None, str(exc)
    return is_gem_document_bytes(body)
