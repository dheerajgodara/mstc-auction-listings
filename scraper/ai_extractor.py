from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import requests
from pydantic import BaseModel, Field, ValidationError

from scraper.config import (
    AI_CACHE_DIR,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_APP_NAME,
    OPENROUTER_FALLBACK_MODELS,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    PARSER_VERSION,
    REQUEST_TIMEOUT,
)
from scraper.models import AuctionRecord, LotRecord, PriceParseStatus

logger = logging.getLogger(__name__)

LOW_CONFIDENCE = frozenset({"low", "minimal"})


class AiLotExtraction(BaseModel):
    item_title: Optional[str] = None
    item_description: Optional[str] = None
    start_price_inr: Optional[float] = None
    start_price_text: Optional[str] = None
    price_parse_status: Optional[PriceParseStatus] = None
    pre_bid_emd_amount: Optional[float] = None
    pre_bid_emd_text: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    location: Optional[str] = None
    lot_details_text: Optional[str] = None
    lot_description_text: Optional[str] = None
    lot_parameters_text: Optional[str] = None
    lot_other_details_text: Optional[str] = None
    lot_documents_text: Optional[str] = None


class AiAuctionSummary(BaseModel):
    item_summary: Optional[str] = None
    seller: Optional[str] = None
    location: Optional[str] = None
    pre_bid_emd_amount: Optional[float] = None
    emd_summary: Optional[str] = None
    price_summary: Optional[str] = None


def is_ai_fallback_enabled() -> bool:
    return bool(OPENROUTER_API_KEY)


def extract_from_pdf_with_ai(pdf_text: str, auction_id: str) -> list[LotRecord]:
    """Legacy entry point — returns AI-extracted lots when enabled."""
    if not is_ai_fallback_enabled() or not pdf_text.strip():
        return []
    context = {"auction_id": auction_id, "source": "mstc"}
    data = extract_lot_with_ai(pdf_text, context, lot_id="pdf", pdf_hash=_hash_text(pdf_text))
    if not data:
        return []
    return [
        LotRecord(
            lot_id="1",
            item_title=data.get("item_title") or f"Auction {auction_id}",
            item_description=data.get("item_description"),
            start_price_inr=data.get("start_price_inr"),
            start_price=data.get("start_price_inr"),
            start_price_text=data.get("start_price_text"),
            price_parse_status=data.get("price_parse_status") or "unknown",
            pre_bid_emd_amount=data.get("pre_bid_emd_amount"),
            pre_bid_emd_text=data.get("pre_bid_emd_text"),
            quantity=data.get("quantity"),
            unit=data.get("unit"),
            location=data.get("location"),
            lot_details_text=data.get("lot_details_text"),
            lot_description_text=data.get("lot_description_text"),
            lot_parameters_text=data.get("lot_parameters_text"),
            lot_other_details_text=data.get("lot_other_details_text"),
            lot_documents_text=data.get("lot_documents_text"),
        )
    ]


def should_use_ai(auction: AuctionRecord, lot: LotRecord | None = None) -> bool:
    if not is_ai_fallback_enabled():
        return False
    if auction.parse_confidence in LOW_CONFIDENCE:
        return True
    if not auction.lots:
        return True
    target = lot or (auction.lots[0] if auction.lots else None)
    if target is None:
        return True
    if not (target.item_title or "").strip():
        return True
    if not (target.item_description or "").strip() and (
        target.lot_description_text or target.lot_details_text
    ):
        return False
    if not (target.item_description or "").strip():
        return True
    if target.price_parse_status in {"missing", "unknown"} and not target.start_price_text:
        return True
    if auction.pre_bid_emd_required and target.pre_bid_emd_amount is None:
        return True
    section_text = " ".join(
        filter(
            None,
            [
                target.lot_details_text,
                target.lot_description_text,
                target.lot_parameters_text,
                target.lot_other_details_text,
                target.lot_documents_text,
            ],
        )
    )
    if section_text and not any(
        [
            target.lot_details_text,
            target.lot_description_text,
            target.lot_parameters_text,
        ]
    ):
        return True
    return False


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(auction_id: str, lot_id: str, pdf_hash: str, kind: str) -> Path:
    safe_lot = re.sub(r"[^\w.-]+", "_", lot_id)[:80]
    return AI_CACHE_DIR / f"{auction_id}_{safe_lot}_{pdf_hash}_{PARSER_VERSION}_{kind}.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _model_chain() -> list[str]:
    models: list[str] = []
    for model in [OPENROUTER_MODEL, *OPENROUTER_FALLBACK_MODELS]:
        if model and model not in models:
            models.append(model)
    return models


def _call_openrouter(prompt: str) -> dict[str, Any] | None:
    if not OPENROUTER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL
    if OPENROUTER_APP_NAME:
        headers["X-Title"] = OPENROUTER_APP_NAME

    for model in _model_chain():
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract auction data from Indian government auction text. "
                        "Return valid JSON only. Use INR numbers without commas."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            resp = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=body,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning("OpenRouter model %s failed: HTTP %s", model, resp.status_code)
                continue
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.warning("OpenRouter model %s error: %s", model, exc)
            continue
    return None


def _merge_lot_fields(existing: LotRecord, ai_data: dict[str, Any]) -> dict[str, Any]:
    validated = AiLotExtraction.model_validate(ai_data)
    updates: dict[str, Any] = {}
    for field_name, value in validated.model_dump(exclude_none=True).items():
        if value is None:
            continue
        current = getattr(existing, field_name, None)
        if field_name in {"start_price_inr", "start_price", "pre_bid_emd_amount", "bid_increment"}:
            if current is not None:
                continue
        elif current not in (None, "", []):
            continue
        updates[field_name] = value
    if "start_price_inr" in updates and existing.start_price is None:
        updates["start_price"] = updates["start_price_inr"]
    return updates


def extract_lot_with_ai(
    lot_block_or_sections: str,
    auction_context: dict[str, Any],
    *,
    lot_id: str = "1",
    pdf_hash: str | None = None,
    existing: LotRecord | None = None,
) -> dict[str, Any]:
    auction_id = str(auction_context.get("auction_id") or "unknown")
    digest = pdf_hash or _hash_text(lot_block_or_sections)
    cache_file = _cache_path(auction_id, lot_id, digest, "lot")
    cached = _read_cache(cache_file)
    if cached is not None:
        if existing:
            return _merge_lot_fields(existing, cached)
        return cached

    prompt = (
        "Extract one auction lot as JSON with keys: "
        "item_title, item_description, start_price_inr, start_price_text, "
        "price_parse_status, pre_bid_emd_amount, pre_bid_emd_text, quantity, unit, location, "
        "lot_details_text, lot_description_text, lot_parameters_text, "
        "lot_other_details_text, lot_documents_text.\n"
        f"Auction context: {json.dumps(auction_context, ensure_ascii=False)}\n"
        f"Lot text:\n{lot_block_or_sections[:12000]}"
    )
    raw = _call_openrouter(prompt)
    if not raw:
        return {}
    try:
        validated = AiLotExtraction.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        logger.warning("AI lot validation failed for %s/%s: %s", auction_id, lot_id, exc)
        return {}
    _write_cache(cache_file, validated)
    if existing:
        return _merge_lot_fields(existing, validated)
    return validated


def extract_auction_summary_with_ai(
    auction_text: str,
    auction_context: dict[str, Any],
    *,
    pdf_hash: str | None = None,
    existing: AuctionRecord | None = None,
) -> dict[str, Any]:
    auction_id = str(auction_context.get("auction_id") or "unknown")
    digest = pdf_hash or _hash_text(auction_text)
    cache_file = _cache_path(auction_id, "summary", digest, "auction")
    cached = _read_cache(cache_file)
    if cached is not None:
        return _merge_auction_fields(existing, cached) if existing else cached

    prompt = (
        "Extract auction summary JSON with keys: item_summary, seller, location, "
        "pre_bid_emd_amount, emd_summary, price_summary.\n"
        f"Auction context: {json.dumps(auction_context, ensure_ascii=False)}\n"
        f"Text:\n{auction_text[:12000]}"
    )
    raw = _call_openrouter(prompt)
    if not raw:
        return {}
    try:
        validated = AiAuctionSummary.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        logger.warning("AI auction validation failed for %s: %s", auction_id, exc)
        return {}
    _write_cache(cache_file, validated)
    return _merge_auction_fields(existing, validated) if existing else validated


def _merge_auction_fields(existing: AuctionRecord | None, ai_data: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return ai_data
    validated = AiAuctionSummary.model_validate(ai_data)
    updates: dict[str, Any] = {}
    for field_name, value in validated.model_dump(exclude_none=True).items():
        if value is None:
            continue
        current = getattr(existing, field_name, None)
        if field_name == "pre_bid_emd_amount" and current is not None:
            continue
        if current not in (None, "", []):
            continue
        updates[field_name] = value
    return updates
