"""Provider abstraction for AI enrichment (OpenRouter + mock)."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

import requests

from scraper.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_APP_NAME,
    OPENROUTER_FALLBACK_MODELS,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    REQUEST_TIMEOUT,
)
from scraper.models import AuctionRecord

logger = logging.getLogger(__name__)

_FORBIDDEN_EDITORIAL_PATTERNS = [
    re.compile(r"(?:₹|rs\.?\s*|inr\s*)[\d,]+", re.I),
    re.compile(r"\b(?:emd|earnest)\b", re.I),
    re.compile(r"\b(?:https?://|www\.)", re.I),
    re.compile(r"\b(?:bid now|place bid|winning bid)\b", re.I),
]


def _material_label(material: str) -> str:
    return material.replace("_", " ").strip().title() or "Scrap"


def _editorial_heading(record: AuctionRecord, material: str) -> str:
    material_label = _material_label(material)
    if record.lots:
        primary = (record.lots[0].item_title or "").strip()
        if primary and len(record.lots) == 1:
            return primary[:120]
        if len(record.lots) > 1:
            return f"{material_label} — {len(record.lots)} lots"[:120]
    fallback = (record.display_title or record.item_summary or record.auction_number or record.id).strip()
    if fallback.lower().startswith("bids are invited"):
        return material_label[:120]
    return fallback[:120] or material_label[:120]


def _editorial_buyer_summary(record: AuctionRecord, material: str, location_label: Optional[str]) -> str:
    material_label = _material_label(material)
    parts: list[str] = []
    if location_label:
        parts.append(f"{material_label} listing near {location_label}")
    else:
        parts.append(f"Government {material_label.lower()} auction listing")
    if len(record.lots) > 1:
        parts.append(f"{len(record.lots)} lots in this auction")
    key_lots = []
    for lot in record.lots[:3]:
        title = (lot.item_title or "").strip()
        if title and title not in key_lots:
            key_lots.append(title)
    if key_lots:
        parts.append("Includes " + ", ".join(key_lots))
    summary = ". ".join(parts)
    for pattern in _FORBIDDEN_EDITORIAL_PATTERNS:
        if pattern.search(summary):
            return f"Buyer-readable {material_label.lower()} listing for review."[:400]
    return summary[:400]


def _editorial_lot_summary(lot_title: str, material: str) -> Optional[str]:
    title = lot_title.strip()
    if not title:
        return None
    summary = f"{_material_label(material)} lot: {title}"[:300]
    for pattern in _FORBIDDEN_EDITORIAL_PATTERNS:
        if pattern.search(summary):
            return f"Scrap lot: {title}"[:300]
    return summary


class EnrichmentProvider(ABC):
    @abstractmethod
    def enrich_listing(self, record: AuctionRecord, prompt: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        """Return (parsed_json, model_used)."""


class MockEnrichmentProvider(EnrichmentProvider):
    """Deterministic offline provider for tests and --mock runs."""

    def enrich_listing(self, record: AuctionRecord, prompt: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        material = record.display_material_category or "other_scrap"
        location = record.display_location_city
        state = record.display_location_state or record.state
        location_label = None
        if location and state:
            location_label = f"{location}, {state}"
        elif location or state:
            location_label = location or state

        lots_out = []
        for lot in record.lots[:6]:
            lot_title = (lot.item_title or f"Lot {lot.lot_id}").strip()
            lots_out.append(
                {
                    "lot_id": lot.lot_id,
                    "heading": lot_title[:120],
                    "summary": _editorial_lot_summary(lot_title, material),
                    "tags": [material] if material else [],
                    "confidence": "medium",
                }
            )

        return (
            {
                "clean_heading": _editorial_heading(record, material),
                "buyer_summary": _editorial_buyer_summary(record, material, location_label),
                "clean_location_label": location_label,
                "location_confidence": record.display_location_confidence or "medium",
                "material_tags": [material] if material else [],
                "buyer_intent_tags": ["multi_lot"] if len(record.lots) > 1 else [],
                "risk_notes": [],
                "lots": lots_out,
            },
            "mock/enrichment-v1",
        )


class OpenRouterEnrichmentProvider(EnrichmentProvider):
    def __init__(self, *, allow_network: bool = False) -> None:
        self.allow_network = allow_network
        self.last_error: Optional[str] = None

    def _model_chain(self) -> list[str]:
        models: list[str] = []
        for model in [OPENROUTER_MODEL, *OPENROUTER_FALLBACK_MODELS]:
            if model and model not in models:
                models.append(model)
        return models

    def enrich_listing(self, record: AuctionRecord, prompt: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        self.last_error = None
        if not self.allow_network:
            logger.info("Network disabled; skipping OpenRouter call for %s", record.id)
            self.last_error = "network_disabled"
            return None, None
        if not OPENROUTER_API_KEY:
            logger.info("OPENROUTER_API_KEY not configured; skipping %s", record.id)
            self.last_error = "openrouter_api_key_missing"
            return None, None

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        if OPENROUTER_SITE_URL:
            headers["HTTP-Referer"] = OPENROUTER_SITE_URL
        if OPENROUTER_APP_NAME:
            headers["X-Title"] = OPENROUTER_APP_NAME

        for model in self._model_chain():
            body = {
                "model": model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You enrich Indian government auction listings for buyers. "
                            "Return valid JSON only. Never invent commercial facts."
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
                if resp.status_code in {401, 403}:
                    logger.warning("OpenRouter authentication failed: HTTP %s", resp.status_code)
                    self.last_error = "openrouter_auth_failed"
                    return None, None
                if resp.status_code == 429:
                    logger.warning("OpenRouter rate limit for model %s", model)
                    self.last_error = "openrouter_rate_limited"
                    continue
                if resp.status_code != 200:
                    logger.warning("OpenRouter model %s failed: HTTP %s", model, resp.status_code)
                    self.last_error = f"openrouter_http_{resp.status_code}"
                    continue
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed, model
            except Exception as exc:
                logger.warning("OpenRouter model %s error: %s", model, exc)
                self.last_error = "openrouter_exception"
                continue
        return None, None


def get_provider(*, mock: bool = False, allow_network: bool = False) -> EnrichmentProvider:
    if mock or not allow_network:
        return MockEnrichmentProvider()
    return OpenRouterEnrichmentProvider(allow_network=True)
