from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def research_recency_score(accessed: str) -> float:
    d = _parse_date(accessed)
    if not d:
        return 0.7
    days = (date.today() - d).days
    if days <= 7:
        return 1.0
    if days <= 30:
        return 1.0 - (days - 7) / 46 * 0.5
    if days <= 60:
        return 0.5
    return 0.3


def lot_confidence(lot: dict[str, Any], research_date: str) -> dict[str, Any]:
    lines = lot.get("lines") or []
    has_pdf_evidence = any(ln.get("evidence", {}).get("page_image") for ln in lines)
    has_weights = any(ln.get("unit") == "MT" or ln.get("weight_kg_est") for ln in lines)

    source_quality = 0.9 if has_pdf_evidence and has_weights else 0.7 if has_pdf_evidence else 0.5
    recency = research_recency_score(research_date)
    yield_certainty = 0.9 if has_weights else 0.5

    pct = round(100 * (0.40 * source_quality + 0.35 * recency + 0.25 * yield_certainty), 1)
    return {
        "confidence_pct": pct,
        "confidence_factors": {
            "source_quality": round(source_quality, 2),
            "research_recency": round(recency, 2),
            "yield_certainty": round(yield_certainty, 2),
        },
    }
