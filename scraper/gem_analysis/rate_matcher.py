from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scraper.config import REPO_ROOT

RATES_PATH = REPO_ROOT / "work" / "gem_market_rates.json"


def load_rate_card() -> dict[str, Any]:
    return json.loads(RATES_PATH.read_text(encoding="utf-8"))


def match_rates(material_tags: list[str]) -> list[dict[str, Any]]:
    card = load_rate_card()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    tag_set = set(material_tags)
    for entry in card.get("entries", []):
        entry_tags = set(entry.get("tags") or [])
        if not tag_set & entry_tags:
            continue
        eid = entry["id"]
        if eid in seen:
            continue
        seen.add(eid)
        out.append(
            {
                "id": entry["id"],
                "label": entry["label"],
                "rate_low": entry.get("rate_low"),
                "rate_high": entry.get("rate_high"),
                "rate_typical": entry.get("rate_typical"),
                "unit": entry.get("unit"),
                "region": entry.get("region"),
                "note": entry.get("note"),
                "sources": entry.get("sources") or [],
                "match_reason": f"tags: {', '.join(sorted(tag_set & entry_tags))}",
            }
        )
    return out
