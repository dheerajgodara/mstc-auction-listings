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


def format_indian_number(amount: float | int, *, decimals: int | None = None) -> str:
    """Group digits Indian style (lakhs/crores): last 3 digits, then pairs of 2."""
    n = float(amount)
    negative = n < 0
    n = abs(n)

    if decimals is None:
        decimals = 0 if n == int(n) else 2

    if decimals:
        text = f"{n:.{decimals}f}"
        int_part_str, frac_str = text.split(".")
    else:
        int_part_str = str(int(round(n)))
        frac_str = ""

    s = int_part_str
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts: list[str] = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + f",{last3}"

    result = grouped
    if frac_str:
        result += f".{frac_str}"
    if negative:
        result = f"-{result}"
    return result


def format_inr_amount(amount: float | int, *, decimals: int | None = None) -> str:
    if decimals is None:
        decimals = 0 if float(amount) == int(float(amount)) else 2
    return f"₹{format_indian_number(amount, decimals=decimals)}"


def format_inr_or_dash(amount: float | int | None, *, decimals: int | None = None) -> str:
    if amount is None:
        return "—"
    return format_inr_amount(amount, decimals=decimals)
