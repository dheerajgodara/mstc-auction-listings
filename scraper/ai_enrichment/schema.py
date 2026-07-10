"""Schema validation for listing-level AI enrichment output."""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from scraper.ai_enrichment.taxonomy import normalize_tags
from scraper.config import AI_ENRICHMENT_PROMPT_VERSION, AI_ENRICHMENT_SCHEMA_VERSION
from scraper.models import AiConfidence

PROMPT_VERSION = AI_ENRICHMENT_PROMPT_VERSION
AI_SCHEMA_VERSION = AI_ENRICHMENT_SCHEMA_VERSION

MAX_HEADING_LEN = 120
MAX_SUMMARY_LEN = 400
MAX_LOT_HEADING_LEN = 120
MAX_LOT_SUMMARY_LEN = 300
MAX_MATERIAL_TAGS = 2
MAX_BUYER_INTENT_TAGS = 2

FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "price",
        "start_price",
        "start_price_inr",
        "emd",
        "pre_bid_emd",
        "quantity",
        "unit",
        "opening",
        "closing",
        "seller",
        "gst",
        "tcs",
        "detail_url",
        "pdf_url",
        "source_pdf_url",
        "document_urls",
        "bidding_advice",
    }
)

_FORBIDDEN_VALUE_PATTERNS = [
    re.compile(r"(?:₹|rs\.?\s*|inr\s*)[\d,]+", re.I),
    re.compile(r"\b(?:emd|earnest)\b", re.I),
    re.compile(r"\b(?:https?://|www\.)", re.I),
    re.compile(r"\b(?:bid now|place bid|winning bid)\b", re.I),
]


class AiLotOutput(BaseModel):
    lot_id: str
    heading: str = Field(max_length=MAX_LOT_HEADING_LEN)
    summary: Optional[str] = Field(default=None, max_length=MAX_LOT_SUMMARY_LEN)
    tags: list[str] = Field(default_factory=list)
    confidence: AiConfidence = "medium"


class AiListingOutput(BaseModel):
    clean_heading: str = Field(max_length=MAX_HEADING_LEN)
    buyer_summary: str = Field(max_length=MAX_SUMMARY_LEN)
    clean_location_label: Optional[str] = Field(default=None, max_length=120)
    location_confidence: AiConfidence = "medium"
    material_tags: list[str] = Field(default_factory=list)
    buyer_intent_tags: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list, max_length=8)
    lots: list[AiLotOutput] = Field(default_factory=list)

    @field_validator("lots", mode="before")
    @classmethod
    def _default_lots(cls, value: Any) -> list[Any]:
        return value if value is not None else []


class ValidationResult(BaseModel):
    ok: bool
    output: Optional[AiListingOutput] = None
    rejection_reasons: list[str] = Field(default_factory=list)
    dropped_lot_ids: list[str] = Field(default_factory=list)
    unknown_tags: list[str] = Field(default_factory=list)


def _scan_forbidden_content(text: str, field_name: str) -> list[str]:
    reasons: list[str] = []
    for pattern in _FORBIDDEN_VALUE_PATTERNS:
        if pattern.search(text):
            reasons.append(f"forbidden_commercial_content_in_{field_name}")
            break
    return reasons


def _check_forbidden_keys(raw: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    lower_keys = {str(k).lower() for k in raw.keys()}
    hits = lower_keys & FORBIDDEN_OUTPUT_KEYS
    if hits:
        reasons.append(f"forbidden_keys:{','.join(sorted(hits))}")
    return reasons


def validate_listing_enrichment(
    raw: dict[str, Any],
    *,
    expected_lot_ids: set[str],
) -> ValidationResult:
    reasons: list[str] = list(_check_forbidden_keys(raw))
    unknown_tags: list[str] = []

    try:
        parsed = AiListingOutput.model_validate(raw)
    except Exception as exc:
        return ValidationResult(ok=False, rejection_reasons=[f"schema_invalid:{exc}"])

    for field_name, value in (
        ("clean_heading", parsed.clean_heading),
        ("buyer_summary", parsed.buyer_summary),
        ("clean_location_label", parsed.clean_location_label or ""),
    ):
        if value:
            reasons.extend(_scan_forbidden_content(value, field_name))

    mat_tags, mat_rejected = normalize_tags(parsed.material_tags)
    buyer_tags, buyer_rejected = normalize_tags(parsed.buyer_intent_tags)
    mat_tags = mat_tags[:MAX_MATERIAL_TAGS]
    buyer_tags = buyer_tags[:MAX_BUYER_INTENT_TAGS]
    unknown_tags.extend(mat_rejected)
    unknown_tags.extend(buyer_rejected)

    risk_notes = [n.strip() for n in parsed.risk_notes if n and n.strip()][:8]

    valid_lots: list[AiLotOutput] = []
    dropped: list[str] = []
    seen_lot_ids: set[str] = set()
    for lot in parsed.lots:
        if lot.lot_id not in expected_lot_ids:
            dropped.append(lot.lot_id)
            continue
        if lot.lot_id in seen_lot_ids:
            continue
        lot_reasons: list[str] = []
        lot_reasons.extend(_scan_forbidden_content(lot.heading, "lot_heading"))
        if lot.summary:
            lot_reasons.extend(_scan_forbidden_content(lot.summary, "lot_summary"))
        lot_tags, lot_rejected = normalize_tags(lot.tags)
        lot_tags = lot_tags[:MAX_MATERIAL_TAGS]
        unknown_tags.extend(lot_rejected)
        if lot_reasons:
            dropped.append(lot.lot_id)
            reasons.extend(lot_reasons)
            continue
        valid_lots.append(
            AiLotOutput(
                lot_id=lot.lot_id,
                heading=lot.heading.strip(),
                summary=(lot.summary or "").strip() or None,
                tags=lot_tags,
                confidence=lot.confidence,
            )
        )
        seen_lot_ids.add(lot.lot_id)

    for lot_id in parsed.lots:
        lid = lot_id.lot_id if hasattr(lot_id, "lot_id") else str(lot_id)
        if lid not in expected_lot_ids and lid not in dropped:
            dropped.append(lid)

    if reasons:
        return ValidationResult(
            ok=False,
            rejection_reasons=sorted(set(reasons)),
            dropped_lot_ids=sorted(set(dropped)),
            unknown_tags=sorted(set(unknown_tags)),
        )

    output = AiListingOutput(
        clean_heading=parsed.clean_heading.strip(),
        buyer_summary=parsed.buyer_summary.strip(),
        clean_location_label=(parsed.clean_location_label or "").strip() or None,
        location_confidence=parsed.location_confidence,
        material_tags=mat_tags,
        buyer_intent_tags=buyer_tags,
        risk_notes=risk_notes,
        lots=valid_lots,
    )
    return ValidationResult(
        ok=True,
        output=output,
        dropped_lot_ids=sorted(set(dropped)),
        unknown_tags=sorted(set(unknown_tags)),
    )


def listing_confidence(output: AiListingOutput) -> AiConfidence:
    if output.location_confidence == "low":
        return "low"
    lot_confidences = [lot.confidence for lot in output.lots]
    if lot_confidences and all(c == "low" for c in lot_confidences):
        return "low"
    if output.location_confidence == "high" and (
        not lot_confidences or any(c == "high" for c in lot_confidences)
    ):
        return "high"
    return "medium"
