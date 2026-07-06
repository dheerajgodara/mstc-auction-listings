from __future__ import annotations

import re
from typing import Literal, Optional

from scraper.emd import format_inr_amount

PriceParseStatus = Literal[
    "numeric",
    "range",
    "percentage_based",
    "not_disclosed",
    "missing",
    "unknown",
]

PERCENTAGE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bpercentage\b",
        r"bidding\s+to\s+be\s+done\s+in\s+percentage",
        r"%\s*of\s+Value",
        r"quoted\s+in\s+percentage",
        r"\bpremium\b",
        r"revenue\s+share",
        r"start\s+price\s+in\s+per",
        r"bid\s+increment\s+in\s+per",
    )
]

NOT_DISCLOSED_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"not\s+disclosed",
        r"as\s+per\s+annexure",
        r"see\s+annexure",
        r"as\s+per\s+notice",
        r"rate\s+to\s+be\s+quoted",
        r"as\s+per\s+nit",
        r"tender\s+document",
        r"as\s+per\s+tender",
    )
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_price_signal(text: Optional[str]) -> Optional[PriceParseStatus]:
    if not text:
        return None
    blob = _normalize_text(text)
    for pat in PERCENTAGE_PATTERNS:
        if pat.search(blob):
            return "percentage_based"
    for pat in NOT_DISCLOSED_PATTERNS:
        if pat.search(blob):
            return "not_disclosed"
    return None


def collect_price_text_blobs(
    lots: list,
    *,
    html_data: Optional[dict] = None,
) -> str:
    parts: list[str] = []
    if html_data:
        for key in ("auction_number",):
            if html_data.get(key):
                parts.append(str(html_data[key]))
    for lot in lots:
        if isinstance(lot, dict):
            for key in ("name", "description", "category", "lot_name", "pcb_group", "start_price_text"):
                if lot.get(key):
                    parts.append(str(lot[key]))
        else:
            for attr in (
                "item_title",
                "item_description",
                "category",
                "pcb_group",
                "start_price_text",
                "start_price_label",
            ):
                val = getattr(lot, attr, None)
                if val:
                    parts.append(str(val))
    return " ".join(parts)


def classify_lot_price(
    *,
    start_price_inr: Optional[float] = None,
    start_price_text: Optional[str] = None,
    extra_text: Optional[str] = None,
) -> PriceParseStatus:
    if start_price_inr is not None:
        return "numeric"
    signal = detect_price_signal(start_price_text or extra_text or "")
    if signal:
        return signal
    if start_price_text:
        return "unknown"
    return "unknown"


def resolve_auction_price(
    lots: list,
    *,
    html_data: Optional[dict] = None,
    pdf_lots: Optional[list] = None,
) -> tuple[PriceParseStatus, Optional[str]]:
    numeric_prices: list[float] = []
    for lot in lots:
        price = lot.start_price_inr if hasattr(lot, "start_price_inr") else lot.get("start_price")
        if price is not None:
            numeric_prices.append(float(price))

    if numeric_prices:
        lo, hi = min(numeric_prices), max(numeric_prices)
        if lo == hi:
            if lo <= 1:
                return "numeric", "Floor ₹1 (open bidding)"
            return "numeric", f"Floor {format_inr_amount(lo)}" if lo == int(lo) else f"Floor {format_inr_amount(lo, decimals=2)}"
        lo_s = format_inr_amount(lo) if lo == int(lo) else format_inr_amount(lo, decimals=2)
        hi_s = format_inr_amount(hi) if hi == int(hi) else format_inr_amount(hi, decimals=2)
        return "range", f"Floor {lo_s}–{hi_s}"

    blob = collect_price_text_blobs(lots, html_data=html_data)
    if pdf_lots:
        blob += " " + collect_price_text_blobs(pdf_lots)

    signal = detect_price_signal(blob)
    if signal == "percentage_based":
        return "percentage_based", "Percentage-based bidding"
    if signal == "not_disclosed":
        return "not_disclosed", "See PDF for price"

    # Preserve descriptive price text from lots
    texts: list[str] = []
    for lot in lots:
        t = getattr(lot, "start_price_text", None) if not isinstance(lot, dict) else lot.get("start_price_text")
        if t:
            texts.append(t)
    if texts:
        return "unknown", texts[0]

    if not lots:
        return "missing", None
    return "missing", None


def price_satisfied(status: PriceParseStatus) -> bool:
    return status in ("numeric", "range", "percentage_based", "not_disclosed")
