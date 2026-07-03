"""Build archive catalogs for condemned-vehicle auctions from GeM lot text."""

from __future__ import annotations

import re
from typing import Any


_ABBR = {
    "Ambl": "ambulance",
    "Amb": "Ambassador car",
    "Gypsy": "Mahindra Gypsy 4x4",
    "Blro": "Mahindra Bolero",
    "Bolero": "Mahindra Bolero",
    "Scorpio": "Mahindra Scorpio SUV",
    "Sumo": "Tata Sumo SUV",
    "Victa": "Tata Sumo Victa",
    "Tavera": "Chevrolet Tavera MPV",
    "Omni": "Maruti Omni van",
    "Eeco": "Maruti Eeco van",
    "Esteem": "Maruti Esteem sedan",
    "Jeep": "Jeep / 4x4 utility vehicle",
    "ErWTkr": "earth-mover water tanker",
    "ForWTkr": "Force Traveller water tanker",
    "ForTrvWTkr": "Force Traveller water tanker",
    "TWTkr": "Tata water tanker truck",
    "ALWTkr": "Ashok Leyland water tanker",
    "WTkr": "water tanker truck",
    "TTrk": "Tata truck",
    "TTrkWTkr": "Tata truck water tanker",
    "TrkTDV407": "Tata 407 truck",
    "MDeliveryVan": "Mahindra delivery van",
    "SFC": "Tata 407 SFC truck",
}


def _lot_number(item_name: str) -> str:
    m = re.search(r"Lot\s*No\.?\s*0*(\d+)", item_name, re.I)
    return m.group(1).zfill(2) if m else "00"


def _department(item_name: str) -> str:
    m = re.search(
        r"=>\s*\d+\s+Vehicles?\s+of\s+(.+?)\s*\(",
        item_name,
        re.I | re.S,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m2 = re.search(r"Vehs?\s+of\s+(.+?)\s*\(", item_name, re.I)
    return m2.group(1).strip() if m2 else "Government department (Jammu)"


def _vehicle_count(item_name: str) -> int:
    m = re.search(r"=>\s*(\d+)\s+Vehicles?", item_name, re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d+)\s+Veh", item_name, re.I)
    return int(m2.group(1)) if m2 else 0


def _parse_vehicle_token(token: str) -> dict[str, str]:
    token = token.strip()
    year_m = re.search(r"\b(19|20)\d{2}\b", token)
    year = year_m.group(0) if year_m else ""
    body = token[: year_m.start()].strip() if year_m else token

    reg = body
    make_model = ""
    for abbr, full in sorted(_ABBR.items(), key=lambda x: -len(x[0])):
        if abbr in body:
            idx = body.find(abbr)
            reg = body[:idx].strip()
            make_model = full if abbr == body[idx : idx + len(abbr)] else body[idx:].strip()
            break

    if not make_model:
        parts = body.rsplit(" ", 1)
        if len(parts) == 2 and not re.search(r"\d", parts[1]):
            reg, make_model = parts[0], parts[1]
        else:
            reg = re.sub(r"([a-z])([A-Z])", r"\1 \2", body)
            make_model = reg

    reg = re.sub(r"\s+", " ", reg).strip()
    return {"registration": reg, "make_model": make_model, "year": year}


def _split_vehicles(item_name: str) -> list[str]:
    inner = item_name
    if ")" in item_name:
        chunks = re.findall(r"\(([^()]+)\)", item_name)
        return [c.strip() for c in chunks if c.strip()]
    return []


def _plain_vehicle(v: dict[str, str]) -> str:
    reg = v["registration"]
    mm = v["make_model"]
    year = v["year"]
    extra = ""
    for k, desc in _ABBR.items():
        if k in mm:
            extra = f" This is a **{desc}**."
            break
    yr = f", year **{year}**" if year else ""
    return (
        f"Registration **{reg}** — **{mm}**{yr}.{extra} "
        f"Condemned government vehicle sold **as-is** for scrap metal, parts, or rebuild."
    )


def build_vehicle_catalog(record: dict[str, Any]) -> list[dict[str, Any]]:
    lots: list[dict[str, Any]] = []
    openings = {o["item_name"]: o for o in record.get("opening_items") or []}

    for res in record.get("result_items") or []:
        item_name = res["item_name"]
        lot_code = _lot_number(item_name)
        dept = _department(item_name)
        count = _vehicle_count(item_name) or len(_split_vehicles(item_name))
        tokens = _split_vehicles(item_name)
        items: list[dict[str, Any]] = []

        for i, tok in enumerate(tokens, 1):
            v = _parse_vehicle_token(tok)
            items.append(
                {
                    "sub_code": str(i),
                    "title": f"{v['registration']} — {v['make_model']} {v['year']}".strip(),
                    "description_verbatim": tok,
                    "plain_language": _plain_vehicle(v),
                    "quantity": 1,
                    "unit": "Vehicle",
                    "material_tags": ["condemned_vehicle", "elv", "vehicle_scrap"],
                    "evidence": {"source": "gem_result", "ocr_excerpt": tok},
                }
            )

        summary = (
            f"**Lot {lot_code}** sells **{count} condemned vehicles** from **{dept}** "
            f"(Jammu division, J&K). Each registration is listed separately below. "
            f"Vehicles are **end-of-life government fleet** — sold as-is for scrap, parts, or rebuild. "
            f"H1 bid on GeM: **₹{res.get('winning_bid_inr', 0):,.0f}**."
        )

        op = openings.get(item_name, {})
        lots.append(
            {
                "lot_code": lot_code,
                "gem_item_name": item_name,
                "lot_summary_plain": summary,
                "location": "Jammu Division, Jammu & Kashmir",
                "unit_of_sale": "By Lot (all vehicles together)",
                "document_pages": [],
                "items": items,
                "item_count": len(items),
            }
        )

    lots.sort(key=lambda x: x["lot_code"])
    return lots
