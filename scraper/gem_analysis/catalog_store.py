"""Load hand-crafted or generated archive catalogs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scraper.config import REPO_ROOT
from scraper.gem_analysis.archive_catalog import ARCHIVE_31705

CATALOG_DIR = REPO_ROOT / "work" / "gem_archive_catalogs"
BUILTIN: dict[str, list[dict[str, Any]]] = {"31705": ARCHIVE_31705}


def catalog_meta(auction_id: str) -> dict[str, Any]:
    path = CATALOG_DIR / f"{auction_id}.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("meta"):
            return data["meta"]
    py = Path(__file__).resolve().parent / "catalogs" / f"{auction_id}.py"
    if py.is_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"gem_catalog_meta_{auction_id}", py)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        meta = getattr(mod, "META", None)
        if isinstance(meta, dict):
            return meta
    return {}


def get_archive_catalog(auction_id: str) -> list[dict[str, Any]]:
    path = CATALOG_DIR / f"{auction_id}.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("lots") or []
        if isinstance(data, list):
            return data
    py = Path(__file__).resolve().parent / "catalogs" / f"{auction_id}.py"
    if py.is_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"gem_catalog_{auction_id}", py)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        lots = getattr(mod, f"ARCHIVE_{auction_id}", None) or getattr(mod, "LOTS", None)
        if lots:
            return lots
    if auction_id in BUILTIN:
        return BUILTIN[auction_id]

    # Auto-build vehicle auctions from GeM lot descriptions
    premium = REPO_ROOT / "work" / "gem_premium_auctions.json"
    if premium.is_file():
        data = json.loads(premium.read_text(encoding="utf-8"))
        record = next((a for a in data["auctions"] if a["auction_id"] == auction_id), None)
        if record and re.search(r"\bvehicles?\b|earth moving equipment", record.get("title") or "", re.I):
            from scraper.gem_analysis.vehicle_catalog import build_vehicle_catalog

            return build_vehicle_catalog(record)

        vep_dir = REPO_ROOT / "work" / "gem_premium_docs" / auction_id
        vep_pdf = vep_dir / "Lot_wise_details_of_V_E_P.pdf"
        if not vep_pdf.is_file():
            matches = list(vep_dir.glob("*V*E*P*.pdf")) + list(vep_dir.glob("*Lot_wise*.pdf"))
            vep_pdf = matches[0] if matches else vep_dir / "missing.pdf"
        if vep_pdf.is_file() or re.search(r"V/E/P|Class DEE", record.get("title") or "", re.I):
            if vep_pdf.is_file():
                from scraper.gem_analysis.vep_pdf_parser import build_vep_catalog

                return build_vep_catalog(record, vep_pdf)

        if record.get("auction_id") == "35025" or re.search(r"BRTF|SS&TC", record.get("title") or "", re.I):
            from scraper.gem_analysis.brtf_catalog import build_brtf_catalog

            lots = build_brtf_catalog(record)
            if lots:
                return lots

        if re.search(r"MISCELLANEUOS|MTPS|DVC|power station", record.get("title") or "", re.I):
            from scraper.gem_analysis.scrap_lot_catalog import build_scrap_lot_catalog

            return build_scrap_lot_catalog(record)
    return []
