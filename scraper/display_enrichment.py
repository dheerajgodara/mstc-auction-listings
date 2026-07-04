"""Buyer-facing display enrichment for auction records (additive; raw fields preserved)."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from scraper.models import AuctionRecord, LotRecord

DisplayMaterialCategory = Literal[
    "transmission_scrap",
    "aluminium_conductor",
    "ferrous_scrap",
    "cable_scrap",
    "transformer_oil",
    "vehicle_lot",
    "timber",
    "machinery",
    "coal",
    "minerals",
    "property",
    "other",
]

DisplayLocationConfidence = Literal["high", "medium", "low"]

_INDIAN_STATES = {
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "puducherry",
    "chandigarh",
}

_CITY_ALIASES: dict[str, tuple[str, str | None]] = {
    "ballia": ("Ballia", "Uttar Pradesh"),
    "azamgarh": ("Azamgarh", "Uttar Pradesh"),
    "kanpur": ("Kanpur", "Uttar Pradesh"),
    "panki": ("Kanpur", "Uttar Pradesh"),
    "mumbai": ("Mumbai", "Maharashtra"),
    "panvel": ("Panvel", "Maharashtra"),
    "navi mumbai": ("Navi Mumbai", "Maharashtra"),
    "bangalore": ("Bengaluru", "Karnataka"),
    "bengaluru": ("Bengaluru", "Karnataka"),
    "rajajinagar": ("Bengaluru", "Karnataka"),
    "bhandara": ("Bhandara", "Maharashtra"),
    "gadegaon": ("Gadegaon", "Maharashtra"),
}

_MATERIAL_PATTERNS: list[tuple[re.Pattern[str], DisplayMaterialCategory, str]] = [
    (re.compile(r"tower|transmission|earth\s*wire|acsr|conductor|moose|panther|deer", re.I), "transmission_scrap", "Transmission scrap"),
    (re.compile(r"alumin|aluminium|aluminum", re.I), "aluminium_conductor", "Aluminium conductor"),
    (re.compile(r"cable", re.I), "cable_scrap", "Cable scrap"),
    (re.compile(r"transformer\s*oil|insulating\s*oil", re.I), "transformer_oil", "Transformer oil"),
    (re.compile(r"vehicle|car|bus|truck|auto", re.I), "vehicle_lot", "Vehicle lot"),
    (re.compile(r"timber|wood|teak|sal\b", re.I), "timber", "Timber"),
    (re.compile(r"machinery|machine|plant|equipment", re.I), "machinery", "Machinery"),
    (re.compile(r"\bcoal\b", re.I), "coal", "Coal"),
    (re.compile(r"mineral|ore|bauxite|iron\s*ore", re.I), "minerals", "Minerals"),
    (re.compile(r"property|land|building|flat", re.I), "property", "Property"),
    (re.compile(r"ms\s*scrap|ferrous|iron\s*scrap|steel\s*scrap|hms", re.I), "ferrous_scrap", "Ferrous scrap"),
    (re.compile(r"scrap", re.I), "ferrous_scrap", "Ferrous scrap"),
]

_QTY_NUM_RE = re.compile(r"([\d,]+(?:\.\d+)?)")
_LOT_QTY_IN_TEXT = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(MT|MTS|TON|TONS|KG|KGS|LOT|LOTS)\b",
    re.I,
)


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _title_case_city(name: str) -> str:
    parts = name.split()
    return " ".join(p[:1].upper() + p[1:].lower() if p else "" for p in parts)


def _parse_quantity_mt(quantity: str | None, unit: str | None) -> float | None:
    if not quantity:
        return None
    m = _QTY_NUM_RE.search(quantity.replace(",", ""))
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    u = (unit or "").strip().upper()
    if u in {"KG", "KGS"}:
        return value / 1000.0
    if u in {"MT", "MTS", "TON", "TONS"}:
        return value
    if u in {"LOT", "LOTS"}:
        return None
    return None


def _lot_quantity_mt(lot: LotRecord) -> float | None:
    mt = _parse_quantity_mt(lot.quantity, lot.unit)
    if mt is not None:
        return mt
    blob = " ".join(
        filter(
            None,
            [lot.item_title, lot.item_description, lot.lot_description_text, lot.lot_details_text],
        )
    )
    matches = list(_LOT_QTY_IN_TEXT.finditer(blob))
    if not matches:
        return None
    total = 0.0
    found = False
    for match in matches:
        val = float(match.group(1).replace(",", ""))
        unit = match.group(2).upper()
        if unit.startswith("KG"):
            total += val / 1000.0
            found = True
        elif unit.startswith("MT") or unit.startswith("TON"):
            total += val
            found = True
    return total if found else None


def _format_mt(value: float) -> str:
    if value >= 100:
        return f"{value:,.0f}".rstrip("0").rstrip(".")
    if value >= 10:
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _lot_labels(lots: list[LotRecord], limit: int = 3) -> list[str]:
    labels: list[str] = []
    for lot in lots:
        title = _clean_text(lot.item_title)
        if title and title not in labels:
            labels.append(title)
        if len(labels) >= limit:
            break
    return labels


def _classify_material(blob: str, asset_category: str | None) -> tuple[DisplayMaterialCategory, str]:
    for pattern, key, label in _MATERIAL_PATTERNS:
        if pattern.search(blob):
            return key, label
    if asset_category == "timber":
        return "timber", "Timber"
    if asset_category == "vehicle":
        return "vehicle_lot", "Vehicle lot"
    if asset_category == "machinery":
        return "machinery", "Machinery"
    if asset_category == "coal":
        return "coal", "Coal"
    if asset_category == "minerals":
        return "minerals", "Minerals"
    if asset_category == "property":
        return "property", "Property"
    return "other", "Other"


def _short_material_label(category: DisplayMaterialCategory, blob: str) -> str:
    if category == "transmission_scrap":
        if re.search(r"tower", blob, re.I) and re.search(r"conductor|acsr|earth", blob, re.I):
            return "Transmission Tower & Conductor Scrap"
        if re.search(r"conductor|acsr|moose|panther|deer", blob, re.I):
            return "Conductor Scrap"
        return "Transmission Scrap"
    if category == "aluminium_conductor":
        if re.search(r"cable", blob, re.I):
            return "Aluminium Cable Scrap"
        return "Aluminium Scrap"
    if category == "ferrous_scrap":
        return "Ferrous Scrap"
    if category == "cable_scrap":
        return "Cable Scrap"
    if category == "transformer_oil":
        return "Transformer Oil"
    if category == "vehicle_lot":
        return "Vehicle Lot"
    if category == "timber":
        return "Timber Lot"
    if category == "machinery":
        return "Machinery Lot"
    if category == "coal":
        return "Coal Lot"
    if category == "minerals":
        return "Minerals Lot"
    if category == "property":
        return "Property Lot"
    return "Scrap Lot"


def _normalize_location(
    raw: str | None,
    state: str | None,
    lots: list[LotRecord],
) -> tuple[str | None, str | None, str | None, DisplayLocationConfidence]:
    raw_clean = _clean_text(raw) or _clean_text(lots[0].location if lots else None)
    state_clean = _clean_text(state) or (lots[0].lot_state if lots else None)
    if state_clean:
        state_clean = _title_case_city(state_clean)

    lower = (raw_clean or "").lower()
    city: str | None = None
    inferred_state: str | None = state_clean

    for token, (city_name, alias_state) in _CITY_ALIASES.items():
        if token in lower:
            city = city_name
            inferred_state = inferred_state or alias_state
            break

    if not city and raw_clean:
        # Comma-separated GeM style: Mumbai, Mumbai, MAHARASHTRA
        parts = [p.strip() for p in raw_clean.split(",") if p.strip()]
        for part in parts:
            pl = part.lower()
            if pl in _INDIAN_STATES:
                inferred_state = _title_case_city(part)
                continue
            if part.isdigit() and len(part) == 6:
                continue
            if len(part) >= 3 and not re.search(r"\b(kv|sub.?station|depot|yard|site)\b", pl):
                city = _title_case_city(part)
                break

    if not city and state_clean and raw_clean and len(raw_clean) <= 40:
        city = _title_case_city(raw_clean)

    if city and inferred_state:
        return city, inferred_state, raw_clean or None, "high"
    if city:
        return city, inferred_state, raw_clean or None, "medium"
    if inferred_state and raw_clean:
        return None, inferred_state, raw_clean, "low"
    if raw_clean:
        return None, None, raw_clean, "low"
    return None, None, None, "low"


def _build_quantity_summary(lots: list[LotRecord]) -> tuple[str | None, float | None]:
    if not lots:
        return None, None
    lot_parts: list[tuple[str, float]] = []
    total_mt = 0.0
    has_mt = False
    for lot in lots:
        mt = _lot_quantity_mt(lot)
        label = _clean_text(lot.item_title) or f"Lot {lot.lot_id}"
        if mt is not None and mt > 0:
            lot_parts.append((label, mt))
            total_mt += mt
            has_mt = True

    if has_mt and lot_parts:
        if len(lot_parts) == 1:
            label, mt = lot_parts[0]
            short = label if len(label) <= 40 else _short_material_label("other", label)
            return f"{_format_mt(mt)} MT {short.lower()}", total_mt
        if len(lot_parts) <= 3:
            detail = " · ".join(f"{_format_mt(mt)} MT {lbl}" for lbl, mt in lot_parts)
            return f"{len(lots)} lots · {detail}", total_mt
        top = sorted(lot_parts, key=lambda x: x[1], reverse=True)[:3]
        detail = " · ".join(f"{_format_mt(mt)} MT {lbl}" for lbl, mt in top)
        return f"{len(lots)} lots · {_format_mt(total_mt)} MT total · {detail}", total_mt

    if len(lots) > 1:
        return f"{len(lots)} lots", None
    return None, None


def _build_display_title(
    record: AuctionRecord,
    lots: list[LotRecord],
    material_category: DisplayMaterialCategory,
    total_mt: float | None,
) -> str:
    blob = " ".join(
        filter(
            None,
            [record.item_summary, *(lot.item_title for lot in lots), *(lot.item_description or "" for lot in lots)],
        )
    )
    short_material = _short_material_label(material_category, blob)

    if total_mt and total_mt > 0:
        return f"{_format_mt(total_mt)} MT {short_material}"

    if len(lots) == 1:
        title = _clean_text(lots[0].item_title)
        if title and len(title) <= 80:
            return title
        if title:
            return truncate_title(title, 80)

    summary = _clean_text(record.item_summary)
    if summary and len(summary) <= 90 and not summary.lower().startswith("bids are invited"):
        return summary
    if summary and material_category != "other":
        return short_material
    if summary:
        return truncate_title(summary, 90)
    return short_material


def truncate_title(text: str, max_len: int) -> str:
    text = _clean_text(text)
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1].rsplit(" ", 1)[0]
    return cut + "…"


def normalize_location(
    raw: str | None,
    state: str | None,
    lots: list[LotRecord],
) -> tuple[str | None, str | None, str | None, DisplayLocationConfidence]:
    return _normalize_location(raw, state, lots)


def _compute_display_fields(record: AuctionRecord) -> dict[str, Any]:
    lots = list(record.lots)
    raw_location = _clean_text(record.location) or _clean_text(lots[0].location if lots else None) or None
    city, state, raw_norm, loc_conf = _normalize_location(record.location, record.state, lots)

    blob = " ".join(
        filter(
            None,
            [
                record.item_summary,
                record.location,
                *(lot.item_title for lot in lots),
                *(lot.item_description or "" for lot in lots),
            ],
        )
    )
    mat_key, mat_label = _classify_material(blob, record.asset_category)
    qty_summary, total_mt = _build_quantity_summary(lots)
    display_title = _build_display_title(record, lots, mat_key, total_mt)
    key_lots = _lot_labels(lots, limit=4)

    location_line = None
    if city and state:
        location_line = f"{city}, {state}"
    elif city:
        location_line = city
    elif state:
        location_line = state

    buyer_bits = [b for b in [qty_summary, mat_label, location_line] if b]
    buyer_summary = " · ".join(buyer_bits) if buyer_bits else None

    return {
        "display_title": display_title,
        "display_location_city": city,
        "display_location_state": state,
        "display_location_raw": raw_norm or raw_location,
        "display_quantity_summary": qty_summary,
        "display_material_category": mat_key,
        "display_key_lots": key_lots,
        "display_buyer_summary": buyer_summary,
        "display_location_confidence": loc_conf,
        "display_total_quantity_mt": total_mt,
    }


def enrich_auction_display(record: AuctionRecord) -> AuctionRecord:
    return apply_display_enrichment(record)


def apply_display_enrichment(record: AuctionRecord) -> AuctionRecord:
    fields = _compute_display_fields(record)
    return record.model_copy(update=fields)


def build_display_search_text(record: AuctionRecord) -> str:
    parts = [
        record.display_title or "",
        record.display_buyer_summary or "",
        record.display_location_city or "",
        record.display_location_state or "",
        record.display_location_raw or "",
        record.display_quantity_summary or "",
        getattr(record, "display_material_category", "") or "",
        " ".join(record.display_key_lots or []),
    ]
    return " ".join(p.lower() for p in parts if p)
