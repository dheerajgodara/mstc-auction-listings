"""Parse Class DEE V/E/P (vehicle-equipment-plant) auction catalog PDFs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz


_ROW_LETTERS = list("ABCDEFGHIJKLMNOP")


def _plain_vep(desc: str, em_no: str) -> str:
    d = re.sub(r"\s+", " ", desc).strip()
    extra = ""
    if "accident" in d.lower():
        extra = " Marked **accident / damaged** in the catalogue."
    if "tipper" in d.lower():
        extra += " **Tipper truck** (dump body) for bulk material haulage."
    elif "gypsy" in d.lower():
        extra += " **Maruti Gypsy** 4x4."
    elif "jcb" in d.lower():
        extra += " **JCB 3DX backhoe loader**."
    elif "compressor" in d.lower() or re.search(r"\bcomp\b", d, re.I):
        extra += " **Air compressor** plant."
    elif "dozer" in d.lower() or re.search(r"\bbd\s*\d+", d, re.I):
        extra += " **Bulldozer** crawler plant."
    elif "excav" in d.lower() or "ex 200" in d.lower() or "excv" in d.lower():
        extra += " **Hydraulic excavator**."
    elif "gen set" in d.lower():
        extra += " **Diesel generator**."
    elif "water truck" in d.lower():
        extra += " **Water bowser / tanker truck**."
    elif "soil compactor" in d.lower():
        extra += " **Soil compactor** roller."
    elif "wet mix" in d.lower():
        extra += " **Wet mix macadam (WMM) plant** — road construction batching plant."
    elif "rock drill" in d.lower():
        extra += " **Rock drill** machine (Sandvik make noted)."
    return (
        f"**{d}** — BA/EM number **{em_no}**. Army Class-DEE condemned asset.{extra} "
        f"Sold as-is from **532 SS&TC**."
    )


def _parse_item_block(block: str) -> dict[str, Any] | None:
    lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    desc = re.sub(r"^\([a-d]\)\s*", "", lines[0], flags=re.I).strip()
    em = lines[1] if len(lines) > 1 else ""
    chassis = lines[2] if len(lines) > 2 else ""
    engine = lines[3] if len(lines) > 3 else ""
    if not re.match(r"^\d{1,2}[A-Z]{1,2}-\d", em):
        return None
    letter_m = re.match(r"^\(([a-d])\)", block.strip(), re.I)
    return {
        "sub_code": letter_m.group(1).upper() if letter_m else "?",
        "title": desc,
        "description_verbatim": f"{em} | {chassis} | {engine}",
        "plain_language": _plain_vep(desc, em),
        "quantity": 1,
        "unit": "V/E/P",
        "material_tags": ["condemned_vehicle", "vee_plant", "industrial_equipment"],
        "evidence": {"source": "vep_catalogue_pdf", "ocr_excerpt": block[:200]},
        "ba_em_no": em,
        "chassis_no": chassis,
        "engine_no": engine,
    }


def parse_vep_pdf(pdf_path: Path) -> dict[str, list[dict[str, Any]]]:
    doc = fitz.open(pdf_path)
    text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()

    # Strip header/footer noise
    text = re.sub(r"AUCTION CATALOGUE.*?Eng No\.\s*", "", text, flags=re.S)
    text = re.sub(r"Ser\s*Lot No.*?Page \d+ of \d+\s*", "", text, flags=re.S)

    lots: dict[str, list[dict[str, Any]]] = {}

    # Rows A–P map to lots 1–16; each row has (a)–(d) items
    row_chunks = re.split(r"\n(?=[A-P]\s*\n)", "\n" + text)
    for chunk in row_chunks:
        row_m = re.match(r"^([A-P])\s*\n(\d{1,2})\s*\n", chunk)
        if not row_m:
            continue
        lot_no = row_m.group(2)
        body = chunk[row_m.end() :]
        items: list[dict[str, Any]] = []
        for sub in re.split(r"(?=\([a-d]\)\s)", body, flags=re.I):
            sub = sub.strip()
            if not sub.lower().startswith("("):
                continue
            item = _parse_item_block(sub)
            if item:
                items.append(item)
        if items:
            lots[lot_no] = items

    if lots:
        return lots

    # Fallback: sequential (a) blocks in groups of 4
    blocks = re.findall(
        r"\([a-d]\)\s*[^\n]+(?:\n(?!\([a-d]\))[^\n]+){0,4}",
        text,
        flags=re.I,
    )
    for i in range(0, len(blocks), 4):
        lot_no = str(i // 4 + 1)
        items = []
        for b in blocks[i : i + 4]:
            it = _parse_item_block(b)
            if it:
                items.append(it)
        if items:
            lots[lot_no] = items
    return lots


def build_vep_catalog(record: dict[str, Any], pdf_path: Path) -> list[dict[str, Any]]:
    parsed = parse_vep_pdf(pdf_path)
    catalog: list[dict[str, Any]] = []

    for res in record.get("result_items") or []:
        item_name = res["item_name"]
        m = re.search(r"Lot\s*No\.?\s*(\d+)", item_name, re.I)
        if not m:
            continue
        lot_no = m.group(1)
        items = parsed.get(lot_no, [])
        catalog.append(
            {
                "lot_code": lot_no,
                "gem_item_name": item_name,
                "lot_summary_plain": (
                    f"**V/E/P Lot {lot_no}** — **{len(items)} condemned vehicles, equipment or plants** "
                    f"from **532 SS&TC Class DEE** store. Each item shows type, BA/EM no., chassis and engine. "
                    f"GeM H1: **₹{res.get('winning_bid_inr', 0):,.0f}** ({res.get('acceptance_status', '—')})."
                ),
                "location": "532 SS&TC — Class DEE",
                "unit_of_sale": "By Lot",
                "items": items,
            }
        )
    catalog.sort(key=lambda x: int(x["lot_code"]))
    return catalog
