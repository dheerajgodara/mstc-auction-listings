"""Export hygiene: strip aged-out closings and classify strict QA errors."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from scraper.filters import parse_min_closing_date
from scraper.incremental import stable_listing_key
from scraper.qa_summary import _parse_closing

IST = ZoneInfo("Asia/Kolkata")

_AGED_OUT_RE = re.compile(r"closes before\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_COUNT_FLOOR_RE = re.compile(r"(count|floor|below|min[_ ]?count|too few|empty export)", re.IGNORECASE)


@dataclass
class HygieneResult:
    export: dict[str, Any]
    dropped: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ClassifiedErrors:
    aged_out: list[str] = field(default_factory=list)
    missing_closing: list[str] = field(default_factory=list)
    missing_source: list[str] = field(default_factory=list)
    count_floor: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)

    @property
    def fatal(self) -> list[str]:
        return [
            *self.missing_closing,
            *self.missing_source,
            *self.count_floor,
            *self.other,
        ]

    @property
    def only_aged_out(self) -> bool:
        return bool(self.aged_out) and not self.fatal

    def all_errors(self) -> list[str]:
        return [*self.aged_out, *self.fatal]


def aged_out_fingerprint(errors: list[str] | ClassifiedErrors) -> str:
    """Stable fingerprint of aged-out auction IDs from gate errors."""
    if isinstance(errors, ClassifiedErrors):
        msgs = errors.aged_out
    else:
        msgs = classify_strict_errors(errors).aged_out
    ids: list[str] = []
    for msg in msgs:
        match = re.search(r"record\s+(\S+)\s+closes before", msg, re.IGNORECASE)
        if match:
            ids.append(match.group(1))
    return ",".join(sorted(ids))


def classify_strict_errors(errors: list[str]) -> ClassifiedErrors:
    result = ClassifiedErrors()
    for raw in errors or []:
        err = str(raw)
        lower = err.lower()
        if _AGED_OUT_RE.search(err):
            result.aged_out.append(err)
        elif "missing closing" in lower:
            result.missing_closing.append(err)
        elif "missing source" in lower or "required source missing" in lower:
            result.missing_source.append(err)
        elif _COUNT_FLOOR_RE.search(err) or "production count" in lower:
            result.count_floor.append(err)
        else:
            result.other.append(err)
    return result


def _recalculate_counts(export: dict[str, Any], auctions: list[dict[str, Any]]) -> None:
    export["auctions"] = auctions
    export["count"] = len(auctions)
    stats = dict(export.get("stats") or {})
    by_source: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    for auction in auctions:
        by_source[str(auction.get("source") or "unknown")] += 1
        by_category[str(auction.get("asset_category") or "unknown")] += 1
    stats["by_source"] = dict(by_source)
    stats["by_category"] = dict(by_category)
    stats["total_lots_in_export"] = sum(len(a.get("lots") or []) for a in auctions)
    export["stats"] = stats


def poison_threshold(export_count: int) -> int:
    return max(50, int(export_count * 0.05))


def strip_aged_out_auctions(
    export: dict[str, Any],
    *,
    min_closing_date: str,
    allow_large_aged_out_strip: bool = False,
) -> HygieneResult:
    """Drop auctions whose closing is strictly before min_closing_date (IST midnight)."""
    min_closing = parse_min_closing_date(min_closing_date)
    auctions = list(export.get("auctions") or [])
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    warnings: list[str] = []

    for auction in auctions:
        closing = _parse_closing(auction.get("closing"))
        if closing is not None and closing < min_closing:
            dropped.append(
                {
                    "id": auction.get("id") or auction.get("source_auction_id"),
                    "source": auction.get("source"),
                    "closing": closing.isoformat(),
                    "key": stable_listing_key(auction),
                }
            )
            continue
        kept.append(auction)

    threshold = poison_threshold(len(auctions))
    if dropped and len(dropped) > threshold and not allow_large_aged_out_strip:
        raise RuntimeError(
            f"aged-out strip poison guard: would drop {len(dropped)} of {len(auctions)} "
            f"(threshold {threshold}); refusing unless allow_large_aged_out_strip=True"
        )

    out = dict(export)
    _recalculate_counts(out, kept)
    if dropped:
        hygiene_stats = dict((out.get("stats") or {}).get("export_hygiene") or {})
        hygiene_stats["dropped_aged_out"] = len(dropped)
        hygiene_stats["min_closing_date"] = min_closing_date
        hygiene_stats["dropped_keys"] = [d["key"] for d in dropped[:50]]
        stats = dict(out.get("stats") or {})
        stats["export_hygiene"] = hygiene_stats
        out["stats"] = stats
        warnings.append(f"stripped {len(dropped)} aged-out auction(s) before {min_closing_date}")

    return HygieneResult(export=out, dropped=dropped, warnings=warnings)


def apply_quarantine_skips(
    export: dict[str, Any],
    quarantine_ids: set[str] | frozenset[str],
    *,
    min_count: int | None = None,
) -> HygieneResult:
    """Remove quarantined stable keys from export. Hard-fails if count would breach floor."""
    if not quarantine_ids:
        return HygieneResult(export=export, dropped=[], warnings=[])

    auctions = list(export.get("auctions") or [])
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for auction in auctions:
        key = stable_listing_key(auction)
        if key in quarantine_ids:
            dropped.append(
                {
                    "id": auction.get("id") or auction.get("source_auction_id"),
                    "source": auction.get("source"),
                    "closing": auction.get("closing"),
                    "key": key,
                    "reason": "quarantine",
                }
            )
            continue
        kept.append(auction)

    if min_count is not None and len(kept) < int(min_count):
        raise RuntimeError(
            f"quarantine skip would leave {len(kept)} auctions below min_count={min_count}; "
            "clear quarantine or fix export"
        )

    out = dict(export)
    _recalculate_counts(out, kept)
    warnings: list[str] = []
    if dropped:
        stats = dict(out.get("stats") or {})
        hygiene = dict(stats.get("export_hygiene") or {})
        hygiene["quarantine_skipped"] = len(dropped)
        hygiene["quarantine_keys"] = [d["key"] for d in dropped[:50]]
        stats["export_hygiene"] = hygiene
        out["stats"] = stats
        warnings.append(f"skipped {len(dropped)} quarantined auction(s)")

    return HygieneResult(export=out, dropped=dropped, warnings=warnings)


def closing_passes_min(record: dict[str, Any], min_closing: datetime) -> bool:
    closing = _parse_closing(record.get("closing"))
    if closing is None:
        return False
    return closing >= min_closing


def format_dropped_telegram_note(dropped: list[dict[str, Any]]) -> str:
    n = len(dropped)
    if n <= 0:
        return ""
    if n <= 3:
        ids = ", ".join(str(d.get("id") or d.get("key") or "?") for d in dropped)
        return f"dropped {n} aged-out ({ids})"
    return f"dropped {n} aged-out"
