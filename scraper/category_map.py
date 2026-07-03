from __future__ import annotations

import re
from typing import Optional

from scraper.models import AssetCategory

DEFAULT_EXCLUDE_CATEGORIES = frozenset({"property", "lease", "land", "building"})

_CATEGORY_KEYWORDS: list[tuple[AssetCategory, tuple[str, ...]]] = [
    ("vehicle", ("vehicle", "car", "bus", "truck", "elv", "end of life", "automobile", "motor")),
    ("scrap", ("scrap", "metal scrap", "iron scrap", "steel scrap", "non-ferrous", "gi sheet", "metallic")),
    ("machinery", ("machinery", "machine", "plant", "equipment", "industrial", "compressor", "generator")),
    ("ewaste", ("e-waste", "ewaste", "electronic waste", "e waste", "it asset", "computer")),
    ("coal", ("coal", "lignite", "coke")),
    ("minerals", ("mineral", "ore", "bauxite", "limestone", "dolomite", "manganese")),
    ("timber", ("timber", "wood", "log", "plywood", "teak")),
    ("property", ("property", "land", "building", "lease", "sublet", "flat", "plot", "immovable")),
]


def _normalize_text(*parts: Optional[str]) -> str:
    return " ".join(p.strip().lower() for p in parts if p and p.strip())


def _match_keywords(text: str) -> Optional[AssetCategory]:
    if not text:
        return None
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return category
    return None


def normalize_mstc_category(
    *,
    category: Optional[str] = None,
    product_type: Optional[str] = None,
    lot_title: Optional[str] = None,
    lot_description: Optional[str] = None,
) -> Optional[AssetCategory]:
    text = _normalize_text(category, product_type, lot_title, lot_description)
    return _match_keywords(text) or ("other" if text else None)


def normalize_gem_category(
    *,
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[AssetCategory]:
    text = _normalize_text(category, sub_category, title)
    return _match_keywords(text) or ("other" if text else None)


def normalize_eauction_category(
    *,
    product_category: Optional[str] = None,
    sub_category: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[AssetCategory]:
    text = _normalize_text(product_category, sub_category, title)
    return _match_keywords(text) or ("other" if text else None)


def should_exclude_category(
    category: Optional[AssetCategory],
    *,
    exclude: frozenset[str] | None = None,
    source: str = "mstc",
) -> bool:
    """Exclude property/lease categories for non-MSTC sources by default."""
    if not category:
        return False
    if source == "mstc":
        return False
    blocked = exclude if exclude is not None else DEFAULT_EXCLUDE_CATEGORIES
    return category in blocked or any(
        token in category for token in blocked if len(token) > 3
    )


def slugify_category_label(label: Optional[str]) -> Optional[AssetCategory]:
    if not label:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
    return _match_keywords(cleaned) or "other"
