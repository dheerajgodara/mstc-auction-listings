from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.filters import parse_min_closing_date
from scraper.import_tracking import stable_auction_key

IST = ZoneInfo("Asia/Kolkata")


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(IST) if value.tzinfo else value.replace(tzinfo=IST)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(IST) if parsed.tzinfo else parsed.replace(tzinfo=IST)


def load_export(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _future_records(records: list[dict[str, Any]], *, min_closing_date: str) -> list[dict[str, Any]]:
    min_dt = parse_min_closing_date(min_closing_date)
    future: list[dict[str, Any]] = []
    for record in records:
        closing = _parse_dt(record.get("closing"))
        if closing is not None and closing >= min_dt:
            future.append(record)
    return future


def source_counts(data: dict[str, Any] | None) -> dict[str, int]:
    if not data:
        return {}
    return dict(Counter(a.get("source") or "mstc" for a in data.get("auctions") or []))


def apply_missing_source_fallback(
    candidate: dict[str, Any],
    *,
    previous_export: dict[str, Any] | None,
    min_closing_date: str,
    fallback_sources: list[str] | tuple[str, ...] = ("mstc", "gem_forward", "eauction"),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Carry forward still-future records for source-wide or partial source misses.

    It fills configured sources when the candidate has zero records for that
    source, or when discovery marked the source incomplete because only some
    offices/pages were reachable. It never overwrites freshly scraped records.
    """
    if not previous_export:
        return candidate, {"applied": False, "sources": {}}

    candidate = deepcopy(candidate)
    auctions = list(candidate.get("auctions") or [])
    current_counts = source_counts(candidate)
    previous_records = list(previous_export.get("auctions") or [])

    existing_keys = {stable_auction_key(a) for a in auctions}
    sources_report: dict[str, Any] = {}

    source_stats = (candidate.get("stats") or {}).get("source_stats") or {}

    for source in fallback_sources:
        source_incomplete = (source_stats.get(source) or {}).get("complete") is False
        if current_counts.get(source, 0) > 0 and not source_incomplete:
            continue
        prior_for_source = [a for a in previous_records if (a.get("source") or "mstc") == source]
        future = _future_records(prior_for_source, min_closing_date=min_closing_date)
        carried: list[dict[str, Any]] = []
        for record in future:
            key = stable_auction_key(record)
            if key in existing_keys:
                continue
            copy = deepcopy(record)
            warnings = list(copy.get("warnings") or [])
            note = (
                f"{source} carried forward from previous production; "
                + ("source discovery incomplete this run" if source_incomplete else "source returned zero records this run")
            )
            if note not in warnings:
                warnings.append(note)
            copy["warnings"] = warnings
            carried.append(copy)
            existing_keys.add(key)

        if carried:
            auctions.extend(carried)
            sources_report[source] = {
                "status": "carried_forward",
                "previous_count": len(prior_for_source),
                "carried_forward": len(carried),
                "reason": "source discovery incomplete" if source_incomplete else "candidate source count was zero",
            }

    if not sources_report:
        return candidate, {"applied": False, "sources": {}}

    candidate["auctions"] = auctions
    candidate["count"] = len(auctions)
    stats = dict(candidate.get("stats") or {})
    stats["by_source"] = source_counts(candidate)
    stats["total_lots_in_export"] = sum(len(a.get("lots") or []) for a in auctions)
    stats["source_fallback"] = {
        "applied": True,
        "sources": sources_report,
        "min_closing_date": min_closing_date,
    }
    candidate["stats"] = stats
    return candidate, stats["source_fallback"]
