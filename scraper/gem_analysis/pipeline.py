from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import REPO_ROOT
from scraper.gem_analysis.acceptance import p_success
from scraper.gem_analysis.catalog import get_catalog
from scraper.gem_analysis.confidence import lot_confidence
from scraper.gem_analysis.constants import RESEARCH_CITATIONS
from scraper.gem_analysis.cost_engine import value_auction, value_lot

IST = ZoneInfo("Asia/Kolkata")
WORK = REPO_ROOT / "work"
PREMIUM_JSON = WORK / "gem_premium_auctions.json"
ANALYSIS_DIR = WORK / "gem_premium_analysis"
DOCS_DIR = WORK / "gem_premium_docs"
BUILD_DIR = REPO_ROOT / "gem-reports" / "build"


def _margin_drivers(lot: dict[str, Any], base: dict[str, Any]) -> list[str]:
    drivers = []
    h1 = lot.get("h1_inr") or 0
    gross = base.get("gross_inr") or 0
    if h1 and gross < h1 * 0.85:
        drivers.append(f"Gross resale ₹{gross:,.0f} is below H1 ₹{h1:,.0f}")
    if lot.get("flags"):
        drivers.append(f"Regulatory flags: {', '.join(lot['flags'])}")
    if base.get("margin_pct", 0) < -10:
        drivers.append("Heavy logistics/disposal drag on mixed lot")
    if not drivers:
        drivers.append("Resale value covers purchase after costs")
    return drivers


def build_analysis(auction_id: str) -> dict[str, Any]:
    data = json.loads(PREMIUM_JSON.read_text(encoding="utf-8"))
    record = next(a for a in data["auctions"] if a["auction_id"] == auction_id)
    catalog = get_catalog(auction_id)
    if not catalog:
        raise ValueError(f"No catalogue for auction {auction_id}")

    results_by_lot = {r["item_name"]: r for r in record.get("result_items") or []}
    opening_by_lot = {o["item_name"]: o for o in record.get("opening_items") or []}
    seq = sorted(
        data["auctions"],
        key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or 0),
    )
    sequence = next(i + 1 for i, a in enumerate(seq) if a["auction_id"] == auction_id)

    lots_out: list[dict[str, Any]] = []
    research_date = RESEARCH_CITATIONS[0]["accessed"]

    for cat in catalog:
        code = cat["lot_code"]
        res = results_by_lot.get(code, {})
        op = opening_by_lot.get(code, {})
        lot = {
            **cat,
            "opening_inr": op.get("opening_price_inr"),
            "h1_inr": res.get("winning_bid_inr"),
            "bidder": res.get("winning_bidder"),
            "status": res.get("acceptance_status") or "Unknown",
        }
        scenarios = {sc: value_lot(lot, sc) for sc in ("best", "base", "worst")}
        lot["scenarios"] = scenarios
        lot["verdict_base"] = scenarios["base"]["verdict"]
        lot.update(lot_confidence(lot, research_date))
        lot["p_success_pct"] = p_success(lot["status"], lot.get("flags"))
        lot["margin_drivers"] = _margin_drivers(lot, scenarios["base"])
        lots_out.append(lot)

    scenarios = value_auction(lots_out)
    h1_total = sum(lot.get("h1_inr") or 0 for lot in lots_out)
    accepted_h1 = sum(
        lot.get("h1_inr") or 0 for lot in lots_out if lot.get("status") == "Accepted"
    )
    conf_weighted = (
        sum((lot.get("h1_inr") or 0) * lot.get("confidence_pct", 0) for lot in lots_out) / h1_total
        if h1_total
        else 0
    )

    return {
        "schema_version": "2.0",
        "auction_id": auction_id,
        "sequence": sequence,
        "meta": {
            "title": record.get("title") or "",
            "seller": record.get("seller_name") or "",
            "region": "Visakhapatnam",
            "category": record.get("category") or "",
            "auction_date": "2026-03-18",
            "analysed_at": datetime.now(IST).isoformat(),
            "gem_urls": {
                "notice": f"https://forwardauction.gem.gov.in{record.get('notice_path', '')}",
                "result": f"https://forwardauction.gem.gov.in{record.get('result_path', '')}",
            },
        },
        "scenarios": scenarios,
        "summary": {
            "total_h1_inr": h1_total,
            "accepted_h1_inr": accepted_h1,
            "lot_count": len(lots_out),
            "accepted_lot_count": sum(1 for l in lots_out if l.get("status") == "Accepted"),
            "portfolio_confidence_pct": round(conf_weighted, 1),
            "weighted_p_success_pct": round(
                sum((lot.get("h1_inr") or 0) * lot.get("p_success_pct", 0) for lot in lots_out) / h1_total,
                1,
            )
            if h1_total
            else 0,
        },
        "lots": lots_out,
        "research_citations": RESEARCH_CITATIONS,
        "assumptions": [
            "Industrial equipment reuse values are estimates for working-condition resale.",
            "Transport modeled at 35 km from MO(V) Old Site to melt yard.",
            "GST RCM 18% with full ITC recovery — cash-flow float only.",
        ],
        "assets": {
            "pdfs": ["docs/Tender_Document.pdf"],
            "page_images": [f"images/page-{i:02d}.png" for i in range(1, 5)],
        },
        "navigation": {
            "prev_id": seq[sequence - 2]["auction_id"] if sequence > 1 else None,
            "next_id": seq[sequence]["auction_id"] if sequence < len(seq) else None,
        },
    }


def prepare_build_assets(auction_id: str, analysis: dict[str, Any]) -> Path:
    out = BUILD_DIR / "auctions" / auction_id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "docs").mkdir()
    (out / "images").mkdir()

    src = DOCS_DIR / auction_id
    for pdf in src.glob("*.pdf"):
        if "Tender" in pdf.name or "tender" in pdf.name:
            shutil.copy2(pdf, out / "docs" / "Tender_Document.pdf")
    for img in (src / "images").glob("*.png"):
        shutil.copy2(img, out / "images" / img.name)

    (out / "data.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def run_pipeline(auction_id: str, *, html: bool = True) -> Path:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    analysis = build_analysis(auction_id)
    seq = analysis["sequence"]
    json_path = ANALYSIS_DIR / f"{seq:02d}_auction_{auction_id}.json"
    json_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

    out_dir = prepare_build_assets(auction_id, analysis)
    if html:
        from scraper.gem_analysis.report_builder import build_auction_html, build_hub_html

        build_auction_html(analysis, out_dir / "index.html")
        build_hub_html()
    return out_dir
