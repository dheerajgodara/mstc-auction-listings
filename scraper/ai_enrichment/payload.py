"""Compact listing payload and prompt builder for AI enrichment."""

from __future__ import annotations

import json
from typing import Any

from scraper.ai_enrichment.schema import AI_SCHEMA_VERSION, PROMPT_VERSION
from scraper.ai_enrichment.taxonomy import BUYER_INTENT_TAGS, MATERIAL_TAGS
from scraper.display_enrichment import apply_display_enrichment
from scraper.models import AuctionRecord, LotRecord

MAX_PROMPT_CHARS = 8000
MAX_TOP_LOTS = 8
MAX_LOT_TEXT_CHARS = 200


def _lot_compact(lot: LotRecord) -> dict[str, Any]:
    title = (lot.item_title or "").strip()
    desc = (lot.item_description or lot.lot_description_text or "")[:MAX_LOT_TEXT_CHARS].strip()
    return {
        "lot_id": lot.lot_id,
        "title": title,
        "description": desc or None,
        "category": lot.category or lot.product_type,
    }


def _lot_importance(lot: LotRecord) -> float:
    score = 0.0
    if lot.quantity:
        score += 1.0
    if lot.item_description or lot.lot_description_text:
        score += 0.5
    score += min(len(lot.item_title or ""), 80) / 80.0
    return score


def build_listing_payload(record: AuctionRecord) -> dict[str, Any]:
    enriched = apply_display_enrichment(record)
    lots = list(record.lots)
    ranked = sorted(lots, key=_lot_importance, reverse=True)
    top_lots = [_lot_compact(lot) for lot in ranked[:MAX_TOP_LOTS]]
    all_lot_ids = [lot.lot_id for lot in lots]

    has_docs = any(lot.documents for lot in lots)
    has_photos = any(
        lot.photo_file or any(d.type == "photo" for d in lot.documents) for lot in lots
    )

    return {
        "auction_id": record.id,
        "source": record.source,
        "auction_number": record.auction_number,
        "raw_title": record.item_summary,
        "display_title": enriched.display_title,
        "location_raw": record.location,
        "city": enriched.display_location_city,
        "state": enriched.display_location_state or record.state,
        "seller": record.seller,
        "lot_count": len(lots),
        "material_category": enriched.display_material_category,
        "asset_category": record.asset_category,
        "documents_available": has_docs,
        "photos_available": has_photos,
        "all_lot_ids": all_lot_ids,
        "top_lots": top_lots,
    }


def build_enrichment_prompt(record: AuctionRecord) -> tuple[str, dict[str, Any]]:
    payload = build_listing_payload(record)
    system = (
        "You enrich Indian government auction listings for buyers. "
        "Return JSON only. Do NOT invent or restate commercial facts: "
        "no price, EMD, quantity, dates, seller, GST/TCS, URLs, documents, or bidding advice. "
        "Write concise buyer-readable headings, summaries, location labels, and controlled tags."
    )
    user = {
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "instructions": {
            "output_keys": [
                "clean_heading",
                "buyer_summary",
                "clean_location_label",
                "location_confidence",
                "material_tags",
                "buyer_intent_tags",
                "risk_notes",
                "lots",
            ],
            "lot_keys": ["lot_id", "heading", "summary", "tags", "confidence"],
            "heading_max_chars": 120,
            "summary_max_chars": 400,
            "confidence_values": ["high", "medium", "low"],
            "material_tags_allowed": sorted(MATERIAL_TAGS),
            "buyer_intent_tags_allowed": sorted(BUYER_INTENT_TAGS),
            "max_material_tags": 2,
            "max_buyer_intent_tags": 2,
            "tag_rule": "Use only allowed predefined tags. Pick at most 2 material tags and at most 2 buyer intent tags.",
        },
        "listing": payload,
    }
    prompt = f"{system}\n\n{json.dumps(user, ensure_ascii=False)}"
    if len(prompt) > MAX_PROMPT_CHARS:
        compact = dict(user)
        compact["listing"] = {
            **payload,
            "top_lots": payload["top_lots"][:4],
        }
        prompt = f"{system}\n\n{json.dumps(compact, ensure_ascii=False)}"
    return prompt, payload


def payload_stats(payload: dict[str, Any]) -> dict[str, int]:
    serialized = json.dumps(payload, ensure_ascii=False)
    return {
        "chars": len(serialized),
        "lot_count": int(payload.get("lot_count") or 0),
        "top_lots": len(payload.get("top_lots") or []),
        "all_lot_ids": len(payload.get("all_lot_ids") or []),
    }
