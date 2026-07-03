"""Build catalog from GeM scrap lot names (one item per lot)."""

from __future__ import annotations

import re
from typing import Any

from scraper.gem_analysis.plain_language import explain_item, _infer_tags


def build_scrap_lot_catalog(record: dict[str, Any]) -> list[dict[str, Any]]:
    lots: list[dict[str, Any]] = []
    openings = {o["item_name"]: o for o in record.get("opening_items") or []}

    for i, res in enumerate(record.get("result_items") or [], 1):
        title = (res.get("item_name") or "").strip()
        if not title:
            continue
        lot_code = str(i)
        tags = _infer_tags(title)
        plain = explain_item(title, "Lot", 1)
        op = openings.get(title, {})
        lots.append(
            {
                "lot_code": lot_code,
                "gem_item_name": title,
                "lot_summary_plain": (
                    f"**Lot {lot_code}** is a single scrap line from the tender/GeM catalogue: "
                    f"**{title}**. Sold as one bundle on an as-is basis. "
                    f"GeM H1: **₹{res.get('winning_bid_inr', 0):,.0f}**."
                ),
                "location": "See tender document",
                "unit_of_sale": "By Lot",
                "items": [
                    {
                        "sub_code": "A",
                        "title": title,
                        "description_verbatim": title,
                        "plain_language": plain,
                        "quantity": 1,
                        "unit": "Lot",
                        "material_tags": tags,
                        "evidence": {"source": "gem_result", "ocr_excerpt": title},
                    }
                ],
            }
        )
    return lots
