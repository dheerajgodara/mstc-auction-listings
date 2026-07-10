"""Controlled tag taxonomy and synonym normalization for AI enrichment."""

from __future__ import annotations

MATERIAL_TAGS: frozenset[str] = frozenset(
    {
        "transmission_scrap",
        "aluminium_conductor",
        "ferrous_scrap",
        "cable_scrap",
        "transformer_oil",
        "vehicle_lot",
        "timber",
        "coal",
        "minerals",
        "machinery",
        "property",
        "ewaste",
        "other_scrap",
    }
)

BUYER_INTENT_TAGS: frozenset[str] = frozenset(
    {
        "large_lot",
        "multi_lot",
        "documents_available",
        "photos_available",
        "site_inspection",
        "closing_soon",
    }
)

RISK_TAGS: frozenset[str] = frozenset(
    {
        "low_location_confidence",
        "missing_document",
        "source_window_limited",
        "price_undisclosed",
    }
)

SOURCE_TYPE_TAGS: frozenset[str] = frozenset(
    {
        "mstc",
        "gem_forward",
        "eauction",
    }
)

ALL_ALLOWED_TAGS: frozenset[str] = MATERIAL_TAGS | BUYER_INTENT_TAGS | RISK_TAGS | SOURCE_TYPE_TAGS

_TAG_SYNONYMS: dict[str, str] = {
    "transmission": "transmission_scrap",
    "transmission scrap": "transmission_scrap",
    "tower scrap": "transmission_scrap",
    "conductor scrap": "transmission_scrap",
    "aluminium": "aluminium_conductor",
    "aluminum": "aluminium_conductor",
    "aluminium scrap": "aluminium_conductor",
    "aluminum scrap": "aluminium_conductor",
    "ferrous": "ferrous_scrap",
    "ms scrap": "ferrous_scrap",
    "steel scrap": "ferrous_scrap",
    "cable": "cable_scrap",
    "transformer oil": "transformer_oil",
    "insulating oil": "transformer_oil",
    "vehicle": "vehicle_lot",
    "vehicles": "vehicle_lot",
    "wood": "timber",
    "large lot": "large_lot",
    "multi lot": "multi_lot",
    "multi-lot": "multi_lot",
    "documents": "documents_available",
    "photos": "photos_available",
    "inspection": "site_inspection",
    "closing soon": "closing_soon",
    "low confidence location": "low_location_confidence",
    "missing docs": "missing_document",
    "missing documents": "missing_document",
    "gem": "gem_forward",
    "gem forward": "gem_forward",
}


def _canonical_key(raw: str) -> str:
    return raw.strip().lower().replace("-", " ").replace("/", " ")


def normalize_tag(raw: str) -> Optional[str]:
    if not raw or not str(raw).strip():
        return None
    key = _canonical_key(str(raw))
    slug = key.replace(" ", "_")
    if slug in ALL_ALLOWED_TAGS:
        return slug
    if key in _TAG_SYNONYMS:
        return _TAG_SYNONYMS[key]
    if slug in _TAG_SYNONYMS:
        return _TAG_SYNONYMS[slug]
    return None


def normalize_tags(raw_tags: list[str]) -> tuple[list[str], list[str]]:
    """Return (accepted_tags, rejected_raw_tags)."""
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in raw_tags:
        canonical = normalize_tag(raw)
        if canonical and canonical not in seen:
            accepted.append(canonical)
            seen.add(canonical)
        elif raw and str(raw).strip():
            rejected.append(str(raw).strip())
    return accepted, rejected
