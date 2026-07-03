from __future__ import annotations

import re
from typing import Literal, Optional

EmdParseStatus = Literal[
    "auction_wise",
    "item_wise",
    "not_required",
    "missing",
    "unknown",
]

NOT_REQUIRED_PHRASE = "not a auto prebid emd auction"


def parse_emd_amount(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned.lower() in {"na", "n/a", "-", "--"}:
        return None
    if re.fullmatch(r"rs\s*0(\.0+)?", cleaned, re.I):
        return 0.0
    digits = re.sub(r"[^\d.]", "", cleaned.replace(",", ""))
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def classify_emd_type_text(emd_type: Optional[str]) -> tuple[Optional[bool], EmdParseStatus]:
    """
    Classify raw EMD type label from HTML or PDF.

    Returns (pre_bid_emd_required, emd_parse_status).
    """
    if not emd_type:
        return None, "unknown"

    normalized = re.sub(r"\s+", " ", emd_type.strip().lower())

    if NOT_REQUIRED_PHRASE in normalized:
        return False, "not_required"
    if "auction wise" in normalized:
        return True, "auction_wise"
    if "item wise" in normalized:
        return True, "item_wise"
    return None, "unknown"


def format_inr_amount(amount: float) -> str:
    if amount == int(amount):
        return f"₹{int(amount):,}"
    return f"₹{amount:,.2f}"
