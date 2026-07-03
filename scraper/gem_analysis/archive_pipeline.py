from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import REPO_ROOT
from scraper.gem_analysis.asset_render import prepare_deploy_assets
from scraper.gem_analysis.catalog_store import catalog_meta, get_archive_catalog
from scraper.gem_analysis.rate_matcher import load_rate_card, match_rates

IST = ZoneInfo("Asia/Kolkata")
WORK = REPO_ROOT / "work"
PREMIUM_JSON = WORK / "gem_premium_auctions.json"
ARCHIVE_DIR = WORK / "gem_premium_analysis"
DOCS_DIR = WORK / "gem_premium_docs"
BUILD_DIR = REPO_ROOT / "gem-reports" / "build"


def _inr(n: float | None) -> str:
    if n is None:
        return "—"
    return f"₹{n:,.0f}"


def build_archive(auction_id: str) -> dict[str, Any]:
    data = json.loads(PREMIUM_JSON.read_text(encoding="utf-8"))
    record = next(a for a in data["auctions"] if a["auction_id"] == auction_id)
    catalog = get_archive_catalog(auction_id)
    if not catalog:
        raise ValueError(f"No archive catalog for {auction_id}")

    results = {r["item_name"]: r for r in record.get("result_items") or []}
    openings = {o["item_name"]: o for o in record.get("opening_items") or []}
    seq_list = sorted(data["auctions"], key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or 0))
    sequence = next(i + 1 for i, a in enumerate(seq_list) if a["auction_id"] == auction_id)

    def _match_lot(lot_def: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        gem_key = lot_def.get("gem_item_name")
        if gem_key and gem_key in results:
            return results[gem_key], openings.get(gem_key, {})
        code = lot_def["lot_code"]
        if code in results:
            return results[code], openings.get(code, {})
        for k, v in results.items():
            if f"Lot No. {code.lstrip('0')}" in k or f"LotNo.{code.lstrip('0')}" in k.replace(" ", ""):
                return v, openings.get(k, {})
        return {}, {}

    lots_out: list[dict[str, Any]] = []
    all_rate_ids: set[str] = set()

    for lot_def in catalog:
        res, op = _match_lot(lot_def)
        items_out = []
        for item in lot_def["items"]:
            tags = item.get("material_tags") or []
            rates = match_rates(tags)
            for r in rates:
                all_rate_ids.add(r["id"])
            items_out.append({**item, "market_rates": rates})

        lots_out.append(
            {
                **lot_def,
                "items": items_out,
                "item_count": len(items_out),
                "opening_price_inr": op.get("opening_price_inr"),
                "increment_price_inr": op.get("increment_price_inr"),
                "result": {
                    "h1_inr": res.get("winning_bid_inr"),
                    "h1_display": _inr(res.get("winning_bid_inr")),
                    "bidder": res.get("winning_bidder"),
                    "bid_datetime": res.get("bid_datetime"),
                    "acceptance_status": res.get("acceptance_status"),
                    "premium_over_opening_pct": res.get("premium_over_opening_pct"),
                },
            }
        )

    total_h1 = sum(lot["result"]["h1_inr"] or 0 for lot in lots_out)
    accepted_h1 = sum(
        lot["result"]["h1_inr"] or 0
        for lot in lots_out
        if lot["result"].get("acceptance_status") == "Accepted"
    )

    rate_card = load_rate_card()
    rate_appendix = [e for e in rate_card.get("entries", []) if e["id"] in all_rate_ids]

    cat_meta = catalog_meta(auction_id)
    title = record.get("title") or ""
    ref_match = __import__("re").search(r"(CTS/[^\s,]+)", title)
    reference_no = cat_meta.get("reference_no") or (ref_match.group(1) if ref_match else "")

    doc_src = DOCS_DIR / auction_id
    manifest_path = doc_src / "manifest.json"
    page_images: list[str] = []
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        page_images = [f"images/{Path(p).name}" for p in manifest.get("pages", [])]
    if not page_images and (doc_src / "images").is_dir():
        page_images = [f"images/{p.name}" for p in sorted((doc_src / "images").glob("*.png"))]

    locations = {lot.get("location") for lot in catalog if lot.get("location")}
    location_summary = cat_meta.get("location_summary") or (
        "; ".join(sorted(locations)[:3]) if locations else "See lot locations in tender"
    )

    return {
        "schema_version": "archive_v1",
        "auction_id": auction_id,
        "sequence": sequence,
        "meta": {
            "title": title,
            "reference_no": reference_no,
            "seller": record.get("seller_name") or "",
            "region": cat_meta.get("region") or "Andhra Pradesh / Telangana / Odisha (multi-site)",
            "location_summary": location_summary,
            "auction_date": cat_meta.get("auction_date") or "",
            "analysed_at": datetime.now(IST).isoformat(),
            "rates_as_of": rate_card.get("updated"),
            "gem_urls": {
                "notice": f"https://forwardauction.gem.gov.in{record.get('notice_path', '')}",
                "result": f"https://forwardauction.gem.gov.in{record.get('result_path', '')}",
            },
        },
        "summary": {
            "lot_count": len(lots_out),
            "total_items": sum(lot["item_count"] for lot in lots_out),
            "total_h1_inr": total_h1,
            "total_h1_display": _inr(total_h1),
            "accepted_h1_inr": accepted_h1,
            "accepted_lot_count": sum(
                1 for lot in lots_out if lot["result"].get("acceptance_status") == "Accepted"
            ),
        },
        "lots": lots_out,
        "rate_appendix": rate_appendix,
        "disclaimer": [
            "Item descriptions and quantities are from the tender document (OCR + manual QA).",
            "H1 bids are from the GeM result page.",
            "Market rates are indicative reference ranges from cited sources — not valuations of this lot.",
            "No profit/loss or bid recommendation is implied.",
        ],
        "assets": {
            "pdfs": [],
            "primary_pdf": None,
            "page_images": page_images,
        },
        "navigation": {
            "prev_id": seq_list[sequence - 2]["auction_id"] if sequence > 1 else None,
            "next_id": seq_list[sequence]["auction_id"] if sequence < len(seq_list) else None,
        },
    }


def prepare_assets(auction_id: str, archive: dict[str, Any]) -> Path:
    out = BUILD_DIR / "auctions" / auction_id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    archive["assets"] = prepare_deploy_assets(auction_id, archive, out)
    (out / "data.json").write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def run_archive_pipeline(auction_id: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive = build_archive(auction_id)
    seq = archive["sequence"]
    out_dir = prepare_assets(auction_id, archive)
    path = ARCHIVE_DIR / f"{seq:02d}_auction_{auction_id}_archive.json"
    path.write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")
    from scraper.gem_analysis.archive_report_builder import build_archive_html, build_hub_html

    build_archive_html(archive, out_dir / "index.html")
    build_hub_html()
    return out_dir
