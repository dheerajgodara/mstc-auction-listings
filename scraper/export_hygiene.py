"""Export hygiene: strip aged-out closings, repair asset paths, classify gate errors."""

from __future__ import annotations

import copy
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
_SCHEMA_RE = re.compile(r"(schema|validation failed|json schema)", re.IGNORECASE)
_ABSOLUTE_PATH_RE = re.compile(
    r"(contains absolute path|absolute preview path)",
    re.IGNORECASE,
)
_BAD_URL_RE = re.compile(
    r"(control characters|invalid.?url|url can.?t contain|found at least)",
    re.IGNORECASE,
)
_RECORD_ID_RE = re.compile(
    r"(?:record\s+(\S+)|absolute preview path on\s+(\S+))",
    re.IGNORECASE,
)

_ABSOLUTE_ASSET_PREFIXES = (
    ("/pdfs/", "pdfs/"),
    ("/docs/", "docs/"),
    ("/thumbs/", "thumbs/"),
)


@dataclass
class HygieneResult:
    export: dict[str, Any]
    dropped: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repaired: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ClassifiedErrors:
    aged_out: list[str] = field(default_factory=list)
    absolute_path: list[str] = field(default_factory=list)
    bad_asset_url: list[str] = field(default_factory=list)
    missing_closing: list[str] = field(default_factory=list)
    missing_source: list[str] = field(default_factory=list)
    count_floor: list[str] = field(default_factory=list)
    schema: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)

    @property
    def site_threatening(self) -> list[str]:
        return [
            *self.missing_closing,
            *self.missing_source,
            *self.count_floor,
            *self.schema,
            *self.other,
        ]

    @property
    def fatal(self) -> list[str]:
        """Backward-compatible alias: site-threatening + leftover recoverable not yet stripped."""
        return self.site_threatening

    @property
    def record_recoverable(self) -> list[str]:
        return [*self.aged_out, *self.absolute_path, *self.bad_asset_url]

    @property
    def only_aged_out(self) -> bool:
        return bool(self.aged_out) and not self.site_threatening and not self.absolute_path and not self.bad_asset_url

    @property
    def only_record_recoverable(self) -> bool:
        return bool(self.record_recoverable) and not self.site_threatening

    def all_errors(self) -> list[str]:
        return [*self.record_recoverable, *self.site_threatening]


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
        elif _ABSOLUTE_PATH_RE.search(err):
            result.absolute_path.append(err)
        elif _BAD_URL_RE.search(err):
            result.bad_asset_url.append(err)
        elif "missing closing" in lower:
            result.missing_closing.append(err)
        elif "missing source" in lower or "required source missing" in lower:
            result.missing_source.append(err)
        elif _COUNT_FLOOR_RE.search(err) or "production count" in lower:
            result.count_floor.append(err)
        elif _SCHEMA_RE.search(err):
            result.schema.append(err)
        else:
            result.other.append(err)
    return result


def is_site_threatening(classified: ClassifiedErrors) -> bool:
    return bool(classified.site_threatening)


def is_record_recoverable(classified: ClassifiedErrors) -> bool:
    """True when only record-level poison/aged-out/absolute-path errors remain."""
    return classified.only_record_recoverable


def extract_record_keys_from_errors(
    errors: list[str] | ClassifiedErrors,
    *,
    export: dict[str, Any] | None = None,
    default_source: str = "mstc",
) -> list[str]:
    """Parse auction IDs from gate error messages into stable keys."""
    if isinstance(errors, ClassifiedErrors):
        msgs = errors.all_errors()
    else:
        msgs = list(errors or [])

    by_id: dict[str, str] = {}
    if export:
        for auction in export.get("auctions") or []:
            aid = str(auction.get("id") or "")
            sid = str(auction.get("source_auction_id") or "")
            key = stable_listing_key(auction)
            if aid:
                by_id[aid] = key
            if sid:
                by_id[sid] = key

    keys: set[str] = set()
    for msg in msgs:
        match = _RECORD_ID_RE.search(msg)
        if not match:
            continue
        aid = (match.group(1) or match.group(2) or "").strip().rstrip(":")
        if not aid:
            continue
        if aid in by_id:
            keys.add(by_id[aid])
        elif ":" in aid:
            keys.add(aid)
        else:
            keys.add(f"{default_source}:{aid}")
    return sorted(keys)


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


def _rewrite_absolute_asset_string(value: str) -> tuple[str, bool]:
    text = value
    if text.startswith(("http://", "https://")):
        # CDN absolute URLs legitimately contain /pdfs/ in the path component.
        return text, False
    changed = False
    for absolute, relative in _ABSOLUTE_ASSET_PREFIXES:
        if absolute in text:
            text = text.replace(absolute, relative)
            changed = True
    # Leading slash only for known asset roots (preview paths like /pdfs/x).
    for relative in ("pdfs/", "docs/", "thumbs/"):
        prefix = f"/{relative}"
        if text.startswith(prefix):
            text = text[1:]
            changed = True
    return text, changed


def _repair_value(value: Any, *, auction_id: Any, repaired: list[dict[str, Any]], field: str) -> Any:
    if isinstance(value, str):
        new_val, changed = _rewrite_absolute_asset_string(value)
        if changed:
            repaired.append(
                {
                    "id": auction_id,
                    "field": field,
                    "from": value[:120],
                    "to": new_val[:120],
                }
            )
            return new_val
        return value
    if isinstance(value, list):
        return [
            _repair_value(item, auction_id=auction_id, repaired=repaired, field=field)
            for item in value
        ]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out[k] = _repair_value(v, auction_id=auction_id, repaired=repaired, field=f"{field}.{k}" if field else k)
        return out
    return value


def repair_absolute_asset_paths(export: dict[str, Any]) -> HygieneResult:
    """Rewrite leading /pdfs|/docs|/thumbs absolute paths to relative asset paths."""
    auctions_in = list(export.get("auctions") or [])
    repaired: list[dict[str, Any]] = []
    auctions_out: list[dict[str, Any]] = []

    for auction in auctions_in:
        aid = auction.get("id") or auction.get("source_auction_id")
        fixed = _repair_value(
            copy.deepcopy(auction),
            auction_id=aid,
            repaired=repaired,
            field="",
        )
        auctions_out.append(fixed)

    out = dict(export)
    out["auctions"] = auctions_out
    warnings: list[str] = []
    if repaired:
        unique = {(r.get("id"), r.get("from")): r for r in repaired}
        repaired = list(unique.values())
        stats = dict(out.get("stats") or {})
        hygiene = dict(stats.get("export_hygiene") or {})
        hygiene["repaired_absolute_paths"] = len(repaired)
        hygiene["repaired_ids"] = sorted({str(r.get("id")) for r in repaired if r.get("id")})[:50]
        stats["export_hygiene"] = hygiene
        out["stats"] = stats
        warnings.append(f"repaired {len(repaired)} absolute asset path(s)")

    return HygieneResult(export=out, dropped=[], warnings=warnings, repaired=repaired)


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


def format_repair_telegram_note(repaired: list[dict[str, Any]]) -> str:
    n = len(repaired)
    if n <= 0:
        return ""
    return f"repaired {n} absolute paths"


def format_quarantine_telegram_note(keys: list[str], *, error_class: str = "poison") -> str:
    n = len(keys)
    if n <= 0:
        return ""
    if n <= 3:
        return f"quarantined {n} · {error_class} ({', '.join(keys)})"
    return f"quarantined {n} · {error_class}"


def rewrite_unsafe_thumb_urls(export: dict[str, Any]) -> dict[str, int]:
    """Rewrite thumbnail_url / preview_images lot segments to safe_lot_dirname form."""
    from scraper.document_cache import rewrite_thumb_lot_segment

    rewritten = 0
    for auction in export.get("auctions") or []:
        for lot in auction.get("lots") or []:
            if not isinstance(lot, dict):
                continue
            previews = lot.get("preview_images")
            if isinstance(previews, list):
                new_previews: list[Any] = []
                changed = False
                for item in previews:
                    if isinstance(item, str):
                        fixed = rewrite_thumb_lot_segment(item)
                        if fixed != item:
                            changed = True
                            rewritten += 1
                        new_previews.append(fixed)
                    elif isinstance(item, dict):
                        row = dict(item)
                        for key in ("url", "thumbnail_url", "src"):
                            val = row.get(key)
                            if isinstance(val, str):
                                fixed = rewrite_thumb_lot_segment(val)
                                if fixed != val:
                                    row[key] = fixed
                                    changed = True
                                    rewritten += 1
                        new_previews.append(row)
                    else:
                        new_previews.append(item)
                if changed:
                    lot["preview_images"] = new_previews
            for doc in lot.get("documents") or []:
                if not isinstance(doc, dict):
                    continue
                thumb = doc.get("thumbnail_url")
                if isinstance(thumb, str):
                    fixed = rewrite_thumb_lot_segment(thumb)
                    if fixed != thumb:
                        doc["thumbnail_url"] = fixed
                        rewritten += 1
    return {"rewritten": rewritten}
