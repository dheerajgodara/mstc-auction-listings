"""Light OCR / PDF spacing cleanup for catalogue text shown on the site."""

from __future__ import annotations

import re

# "DESULPHURISA TION" / "a nnexures" style splits — join short trailing fragments.
_UPPER_SPLIT = re.compile(r"\b([A-Z]{4,})\s+([A-Z]{2,5})\b")
_LOWER_SPLIT = re.compile(r"\b([a-z]{4,})\s+([a-z]{1,3})\b")
_SLASH_SPLIT = re.compile(r"(/)([A-Za-z])\s+([A-Za-z]+)")
_MULTI_SPACE = re.compile(r"[ \t]+")


def cleanup_ocr_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _SLASH_SPLIT.sub(r"\1\2\3", cleaned)
    cleaned = _UPPER_SPLIT.sub(r"\1\2", cleaned)
    cleaned = _LOWER_SPLIT.sub(r"\1\2", cleaned)
    cleaned = "\n".join(_MULTI_SPACE.sub(" ", line).strip() for line in cleaned.split("\n"))
    cleaned = cleaned.strip()
    return cleaned or None
