"""Add readable plain-language explanations to catalog items."""

from __future__ import annotations

import re
from typing import Any


def _infer_tags(desc: str) -> list[str]:
    d = desc.lower()
    tags: list[str] = []
    rules = [
        (r"iron scrap|mt scrap|hms|machinery scrap", ["hms_iron", "mt_scrap"]),
        (r"aluminium|aluminum", ["aluminium_scrap"]),
        (r"brass", ["brass"]),
        (r"cupro.?nickel", ["cupro_nickel"]),
        (r"bearing", ["bearing_scrap"]),
        (r"tyre", ["tyres", "tyre"]),
        (r"wood", ["wood_scrap"]),
        (r"polypropylene|plastic rope|pp rope", ["polypropylene_rope"]),
        (r"wire rope|steel wire", ["steel_wire_rope"]),
        (r"electrical scrap|w/t electrical", ["electrical_scrap", "wt_electrical"]),
        (r"laptop", ["laptop", "mixed_ewaste"]),
        (r"television| tv", ["television", "mixed_ewaste"]),
        (r"computer|pc |aio", ["computer", "mixed_ewaste"]),
        (r"printer|xerox", ["printer", "mixed_ewaste"]),
        (r"mattress", ["mattress", "foam_mattress"]),
        (r"submarine batter", ["lead_acid_battery"]),
        (r"crane|eot", ["crane", "industrial_equipment"]),
        (r"fork.?lift|fork lifter", ["fork_lifter", "industrial_equipment"]),
        (r"generator|diesel engine|cummins", ["generator", "industrial_equipment"]),
        (r"welding|compressor|pump|genie|boat|engine|trolley|tyres", ["industrial_equipment"]),
    ]
    for pat, t in rules:
        if re.search(pat, d):
            tags.extend(t)
    if "ewaste" not in tags and re.search(r"projector|cctv|camera|fan|refrigerator|ac |air condition", d):
        tags.append("mixed_ewaste")
    return list(dict.fromkeys(tags))


def explain_item(title: str, unit: str, qty: float | int) -> str:
    t = title.lower()
    u = unit.upper()
    q = qty

    if "machinery scrap" in t:
        return f"About **{q} tonnes** of old **machinery and plant metal** — broken equipment, frames, and steel structures sold for melting. Not sorted HMS; may need cutting."
    if "iron scrap" in t and u == "MT":
        return f"**{q} metric tonnes of iron/steel scrap** for melting at a steel yard or induction furnace. Standard heavy melting scrap (HMS)."
    if "polypropylene" in t or "plastic rope" in t:
        return f"**{q} tonnes of used plastic (polypropylene) rope** — naval mooring rope past service life. Sold as plastic scrap, not reusable rope."
    if "wire rope" in t or "steel wire rope" in t:
        return f"**{q} tonnes of steel wire rope/cable** — used wire for cranes/ships; sold as ferrous scrap."
    if "trolley mounted cylinder" in t:
        return f"**{q} large gas cylinders** on trolleys (~75 kg each type) — industrial gas bottles, may still hold residue."
    if "hand trolley" in t:
        return f"**{q} hand-pushed warehouse trolleys** for moving stores manually."
    if "fork lift" in t or "fork lifter" in t:
        return f"**{q} fork-lift trucks** — motorised vehicles for lifting pallets; sold as used equipment or scrap."
    if "battery operated trolley" in t:
        return f"**{q} electric battery trolleys** — platform carts for moving goods."
    if "engine" in t and u in ("NOS", "NO"):
        return f"**{q} engine unit(s)** — likely diesel/industrial; for reuse, parts, or scrap."
    if "tyre" in t:
        return f"**{q} used tyres** — vehicle tyres for retreading, crumb rubber, or licensed disposal."
    if "submarine batter" in t:
        return f"**{q} submarine/ship battery cells** — very large lead-acid (or similar) banks. High weight, CPCB-licensed handling required."
    if "television" in t:
        return f"**{q} television sets** — bulk LCD/LED disposal; major e-waste line item."
    if "computer" in t or "all in one" in t:
        return f"**{q} desktop / all-in-one computers** — IT e-waste for refurbishment or dismantling."
    if "laptop" in t:
        return f"**{q} laptop computers** — mixed condition e-waste."
    if "printer" in t or "xerox" in t:
        return f"**{q} printers or photocopiers** — office machines with toner, drums, and metal inside."
    if "mattress" in t:
        return f"**{q} foam/coir mattresses** — bedding; often hard to resell and costly to dispose."
    if "electrical scrap" in t and u == "MT":
        return f"**{q} tonnes of mixed electrical scrap** — wire, panels, and copper-bearing waste sold by weight."
    if "aluminium" in t:
        return f"**{q} tonne(s) of aluminium scrap** — window frames, sheets, mixed ali."
    if "brass" in t:
        return f"**{q} {'pieces' if u.startswith('N') else 'tonne(s)'} of brass** — yellow metal for foundries."
    if "wood" in t:
        return f"**{q} tonnes of wooden scrap** — timber/packing wood."
    if "crane" in t or "eot" in t:
        return f"**{q} crane machine(s)** — heavy lifting equipment; high reuse value if working."
    if "welding" in t:
        return f"**{q} welding machines** — arc/MIG sets for metal work."
    if "compressor" in t:
        return f"**{q} air compressors** — workshop/industrial."
    if "cupro" in t:
        return f"**{q} tonnes cupro-nickel alloy scrap** — valuable marine alloy."
    if "life raft" in t:
        return f"**{q} inflatable life rafts** — marine safety gear; specialised disposal or refurbishment."
    if "boat" in t or "obm" in t or "motor boat" in t:
        return f"**{q} boat/marine craft or outboard motor(s)** — small vessels or engines."
    if "binocular" in t:
        return f"**{q} binoculars** — optical equipment."
    if "fan" in t:
        return f"**{q} electric fans** — ceiling/table/industrial fans."
    if "refrigerator" in t or "washing" in t or "geyser" in t or "micro oven" in t or "air condition" in t:
        return f"**{q} household/appliance units** — white-goods e-waste with refrigerant/compressor considerations."
    if "bearing scrap" in t:
        return f"**{q} tonnes of bearing steel scrap** — alloy bearing rings and housings."
    if "filter" in t:
        return f"**{q} assorted industrial filters** — oil/air filters from equipment."
    if "chair" in t:
        return f"**{q} chairs** — office/mess furniture."
    if "glass bottle" in t or "h2so4" in t:
        return f"**{q} empty chemical glass bottles** — lab acid bottles; low scrap value, handling care needed."
    if "iron scrap" in t and u in ("KG", "KGS"):
        return f"**{q} kg of small-lot iron scrap** — minor weight sold with other items in the lot."
    if "plastic scrap" in t:
        return f"**{q} kg of mixed plastic scrap** — small-quantity plastics from office equipment."
    return (
        f"This line is **{title}** — quantity **{q} {unit}**, as listed in the navy tender. "
        f"Sold as-is from the stated location; inspect before bidding."
    )


def summarize_lot(lot_code: str, items: list[dict[str, Any]], location: str, regulatory: str | None) -> str:
    n = len(items)
    total_mt = sum(i["quantity"] for i in items if i.get("unit") == "MT")
    has_ewaste = any("ewaste" in " ".join(i.get("material_tags") or []) for i in items)
    has_batteries = any("batter" in i.get("title", "").lower() for i in items)
    has_vehicles = any(re.search(r"crane|fork|trolley|boat", i.get("title", ""), re.I) for i in items)

    parts = [
        f"**Lot {lot_code}** at **{location}** contains **{n} separate line items** from the tender."
    ]
    if total_mt:
        parts.append(f"Together they include about **{total_mt:g} metric tonnes** of weight-based scrap.")
    if has_ewaste:
        parts.append("This is an **e-waste / electronics** lot — CPCB authorisation typically required.")
    if has_batteries:
        parts.append("Includes **large batteries** — hazardous waste rules apply.")
    if has_vehicles:
        parts.append("Includes **vehicles or heavy machines** — not plain melt scrap; resale or dismantling.")
    if regulatory:
        parts.append(f"**Regulatory note:** {regulatory}")
    parts.append("Everything is sold **together as one lot** on an *as is, where is* basis.")
    return " ".join(parts)


def enrich_catalog_lot(lot: dict[str, Any]) -> dict[str, Any]:
    items = []
    for item in lot.get("items") or []:
        title = item.get("title") or item.get("description_verbatim") or ""
        tags = item.get("material_tags") or _infer_tags(title)
        plain = item.get("plain_language") or explain_item(title, item.get("unit", ""), item.get("quantity", 0))
        items.append({**item, "material_tags": tags, "plain_language": plain})
    lot = {**lot, "items": items}
    if not lot.get("lot_summary_plain"):
        lot["lot_summary_plain"] = summarize_lot(
            lot.get("lot_code", ""),
            items,
            lot.get("location", ""),
            lot.get("regulatory_notes"),
        )
    lot["item_count"] = len(items)
    return lot
