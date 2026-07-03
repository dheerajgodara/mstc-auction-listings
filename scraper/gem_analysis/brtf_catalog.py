"""Parse army BRTF vehicle catalogue OCR (auction 35025)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scraper.config import REPO_ROOT


def _parse_vehicles_block(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    chunks = re.split(
        r"(?=(?:TATA|MAHINDRA|M/BOLERO|Tata|Mahindra)[^\n]{5,80}\n)",
        text,
        flags=re.I,
    )
    n = 0
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) < 20:
            continue
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0]
        em = ch = eng = ""
        for ln in lines[1:6]:
            if re.search(r"EM\s*No|BA\s*No|BANo", ln, re.I):
                em = re.sub(r".*?:\s*", "", ln, count=1)
            elif re.search(r"CH\s*No|CHNo", ln, re.I):
                ch = re.sub(r".*?:\s*", "", ln, count=1)
            elif re.search(r"Eng\s*No", ln, re.I):
                eng = re.sub(r".*?:\s*", "", ln, count=1)
        n += 1
        items.append(
            {
                "sub_code": str(n),
                "title": title,
                "description_verbatim": f"{em} | {ch} | {eng}".strip(" |"),
                "plain_language": (
                    f"**{title}** — army register **{em or '—'}**, chassis **{ch or '—'}**, engine **{eng or '—'}**. "
                    f"Class-DEE condemned GREF vehicle at Leh (Spituk); sold as-is for scrap or rebuild."
                ),
                "quantity": 1,
                "unit": "Vehicle",
                "material_tags": ["condemned_vehicle", "elv", "vehicle_scrap"],
                "evidence": {"source": "brtf_catalogue_pdf", "ocr_excerpt": chunk[:180]},
            }
        )
    return items


def build_brtf_catalog(record: dict[str, Any]) -> list[dict[str, Any]]:
    ocr_path = REPO_ROOT / "work" / "gem_premium_docs" / "35025" / "Tender_Document_ocr.txt"
    if not ocr_path.is_file():
        return []
    text = ocr_path.read_text(encoding="utf-8")
    lots: list[dict[str, Any]] = []
    results = {r["item_name"]: r for r in record.get("result_items") or []}

    sections = {
        "2": ("501 SS&TC", "501_SS_TC.pdf"),
        "3": ("1034 (I) ESPL", "1034_I_ESPL.pdf"),
    }
    for lot_no, (unit, pdf_tag) in sections.items():
        pdf_esc = pdf_tag.replace(".", r"\.")
        pat = rf"LOT NO\.?\s*0?{lot_no}[\s\S]*?(?===== {pdf_esc} PAGE|===== |\Z)"
        m = re.search(pat, text, re.I)
        if not m:
            m = re.search(rf"LOT NO\.?\s*0?{lot_no}[\s\S]{{200,}}", text, re.I)
        block = m.group(0) if m else ""
        items = _parse_vehicles_block(block)
        gem_key = next((k for k in results if lot_no in k), f"Lot No {lot_no}")
        res = results.get(gem_key, {})
        lots.append(
            {
                "lot_code": lot_no,
                "gem_item_name": gem_key,
                "lot_summary_plain": (
                    f"**Lot {lot_no}** — **{len(items)} condemned GREF vehicles** from **{unit}, Spituk (Leh Ladakh)**. "
                    f"Catalogue year 2026-27. H1: **₹{res.get('winning_bid_inr', 0):,.0f}**."
                ),
                "location": f"{unit}, Spituk, Leh (Ladakh)",
                "unit_of_sale": "By Lot",
                "items": items,
            }
        )
    return lots
