"""Merge validated cached AI enrichment into auction export records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from scraper.ai_enrichment.queue import compute_input_hash, read_cache
from scraper.ai_enrichment.schema import validate_listing_enrichment
from scraper.config import AI_ENRICHMENT_CACHE_DIR, DEFAULT_JSON_OUT
from scraper.models import AuctionRecord, LotRecord


def build_ai_search_text(record: AuctionRecord) -> str:
    if record.ai_status != "ready":
        return ""
    parts = [
        record.ai_clean_heading or "",
        record.ai_buyer_summary or "",
        record.ai_clean_location_label or "",
        " ".join(record.ai_material_tags or []),
        " ".join(record.ai_buyer_intent_tags or []),
        " ".join(record.ai_risk_notes or []),
    ]
    for lot in record.lots:
        if lot.ai_status == "ready":
            parts.extend(
                [
                    lot.ai_heading or "",
                    lot.ai_summary or "",
                    " ".join(lot.ai_tags or []),
                ]
            )
    return " ".join(p.lower() for p in parts if p)


def merge_ai_into_auction(record: AuctionRecord, cached: dict[str, Any]) -> AuctionRecord:
    """Apply validated cache payload onto auction/lot ai_* fields without touching parser fields."""
    if cached.get("status") != "ready":
        updates: dict[str, Any] = {
            "ai_status": cached.get("status", "failed"),
            "ai_rejection_reasons": cached.get("rejection_reasons") or [],
            "ai_input_hash": cached.get("input_hash"),
            "ai_prompt_version": cached.get("prompt_version"),
            "ai_schema_version": cached.get("schema_version"),
        }
        return record.model_copy(update=updates)

    listing_raw = cached.get("listing") or {}
    expected_lot_ids = {lot.lot_id for lot in record.lots}
    validation = validate_listing_enrichment(listing_raw, expected_lot_ids=expected_lot_ids)
    if not validation.ok or validation.output is None:
        return record.model_copy(
            update={
                "ai_status": "rejected",
                "ai_rejection_reasons": validation.rejection_reasons,
                "ai_input_hash": cached.get("input_hash"),
            }
        )

    output = validation.output
    lot_map = {lot.lot_id: lot for lot in output.lots}
    updated_lots: list[LotRecord] = []
    for lot in record.lots:
        ai_lot = lot_map.get(lot.lot_id)
        if ai_lot:
            updated_lots.append(
                lot.model_copy(
                    update={
                        "ai_status": "ready",
                        "ai_heading": ai_lot.heading,
                        "ai_summary": ai_lot.summary,
                        "ai_tags": ai_lot.tags,
                        "ai_confidence": ai_lot.confidence,
                        "ai_model": cached.get("model"),
                        "ai_generated_at": cached.get("generated_at"),
                        "ai_prompt_version": cached.get("prompt_version"),
                        "ai_schema_version": cached.get("schema_version"),
                        "ai_input_hash": cached.get("input_hash"),
                    }
                )
            )
        else:
            updated_lots.append(lot)

    auction_updates = {
        "lots": updated_lots,
        "ai_status": "ready",
        "ai_clean_heading": output.clean_heading,
        "ai_buyer_summary": output.buyer_summary,
        "ai_clean_location_label": output.clean_location_label,
        "ai_location_confidence": output.location_confidence,
        "ai_material_tags": output.material_tags,
        "ai_buyer_intent_tags": output.buyer_intent_tags,
        "ai_risk_notes": output.risk_notes,
        "ai_confidence": cached.get("confidence") or output.location_confidence,
        "ai_model": cached.get("model"),
        "ai_generated_at": cached.get("generated_at"),
        "ai_prompt_version": cached.get("prompt_version"),
        "ai_schema_version": cached.get("schema_version"),
        "ai_input_hash": cached.get("input_hash"),
        "ai_rejection_reasons": [],
    }
    merged = record.model_copy(update=auction_updates)
    ai_search = build_ai_search_text(merged)
    if ai_search:
        merged = merged.model_copy(update={"search_text": f"{merged.search_text} {ai_search}".strip()})
    return merged


def load_cached_enrichment(record: AuctionRecord, cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> Optional[dict[str, Any]]:
    input_hash = compute_input_hash(record)
    return read_cache(record.id, input_hash, cache_dir)


def hydrate_auctions_export(
    export: dict[str, Any],
    *,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
) -> tuple[dict[str, Any], dict[str, int]]:
    auctions_raw = export.get("auctions") or []
    stats = {"ready": 0, "missing": 0, "rejected": 0, "failed": 0, "skipped": 0}
    hydrated: list[dict[str, Any]] = []

    for raw in auctions_raw:
        record = AuctionRecord.model_validate(raw)
        cached = load_cached_enrichment(record, cache_dir=cache_dir)
        if not cached:
            stats["missing"] += 1
            hydrated.append(raw)
            continue
        merged = merge_ai_into_auction(record, cached)
        status = merged.ai_status
        if status in stats:
            stats[status] += 1
        else:
            stats["skipped"] += 1
        hydrated.append(merged.model_dump(mode="json"))

    export = dict(export)
    export["auctions"] = hydrated
    existing_stats = dict(export.get("stats") or {})
    existing_stats["ai_enrichment"] = stats
    export["stats"] = existing_stats
    return export, stats


def hydrate_json_file(
    json_path: Path = DEFAULT_JSON_OUT,
    *,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
    write: bool = True,
) -> dict[str, Any]:
    if not json_path.is_file():
        raise FileNotFoundError(f"Export not found: {json_path}")
    export = json.loads(json_path.read_text(encoding="utf-8"))
    hydrated, stats = hydrate_auctions_export(export, cache_dir=cache_dir)
    if write:
        json_path.write_text(json.dumps(hydrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"stats": stats, "path": str(json_path)}
