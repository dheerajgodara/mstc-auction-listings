"""Export hygiene: strip aged-out closings, repair asset paths, classify gate errors."""

from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.filters import parse_min_closing_boundary
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
    """Drop auctions whose closing is strictly before min_closing_date (YYYY-MM-DD or ISO)."""
    min_closing = parse_min_closing_boundary(min_closing_date)
    auctions = list(export.get("auctions") or [])
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    warnings: list[str] = []

    for auction in auctions:
        closing = _parse_closing(auction.get("closing"))
        if closing is None or closing < min_closing:
            dropped.append(
                {
                    "id": auction.get("id") or auction.get("source_auction_id"),
                    "source": auction.get("source"),
                    "closing": closing.isoformat() if closing else None,
                    "key": stable_listing_key(auction),
                    "auction": auction,
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


def _catalogue_status(auction: dict[str, Any]) -> str:
    lots = auction.get("lots") or []
    has_lots = isinstance(lots, list) and len(lots) > 0
    has_doc = bool(
        auction.get("object_doc_url")
        or auction.get("hostinger_doc_url")
        or auction.get("pdf_url")
    )
    if has_lots and has_doc:
        return "ready"
    if has_doc or has_lots:
        return "pending"
    return "none"


def annotate_archive_auction(
    auction: dict[str, Any],
    *,
    now: datetime | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    """Tag an auction for archive export; return None if outside T-N window or live-eligible."""
    from scraper.filters import (
        archive_reason_for_closing,
        archive_window_start,
        is_archive_eligible,
        is_live_eligible,
    )

    closing = _parse_closing(auction.get("closing"))
    if closing is None:
        return None
    current = now or datetime.now(IST)
    if closing < archive_window_start(now=current):
        return None
    # Live runway rows stay on the main feed only.
    if is_live_eligible(closing, now=current):
        return None
    if not is_archive_eligible(closing, now=current):
        return None
    out = dict(auction)
    inferred = archive_reason_for_closing(closing, now=current)
    out["archive_reason"] = inferred or reason or "aged_out"
    out["catalogue_status"] = _catalogue_status(out)
    out["in_archive"] = True
    return out


def shell_from_ledger_item(
    item: Any,
    *,
    discovery: dict[str, Any] | None = None,
    parsed_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Best-effort archive shell from ledger + optional discovery/parse."""
    disc = discovery or {}
    rec = dict(parsed_record or {})
    aid = str(getattr(item, "source_auction_id", None) or disc.get("id") or "")
    source = str(getattr(item, "source", None) or disc.get("source") or "mstc")
    shell: dict[str, Any] = {
        "id": aid,
        "source_auction_id": aid,
        "source": source,
        "auction_number": disc.get("auction_number") or rec.get("auction_number"),
        "opening": getattr(item, "opening", None) or disc.get("opening") or rec.get("opening"),
        "closing": getattr(item, "closing", None) or disc.get("closing") or rec.get("closing"),
        "seller": getattr(item, "seller", None) or disc.get("seller") or rec.get("seller"),
        "state": getattr(item, "state", None) or disc.get("state") or rec.get("state"),
        "detail_url": getattr(item, "detail_url", None) or disc.get("detail_url") or rec.get("detail_url"),
        "platform": disc.get("platform") or rec.get("platform") or source,
        "asset_category": disc.get("asset_category") or rec.get("asset_category") or "other",
        "region": disc.get("region") or rec.get("region") or getattr(item, "state", None) or "",
        "office": disc.get("office") or rec.get("office") or "",
        "lots": rec.get("lots") if isinstance(rec.get("lots"), list) else [],
        "status": "listing_only" if not (rec.get("lots") or []) else rec.get("status") or "partial",
        "enrichment_status": rec.get("enrichment_status") or "discovery",
    }
    if not shell.get("auction_number"):
        shell["auction_number"] = aid
    for fld in (
        "display_title",
        "title",
        "office",
        "region",
        "pdf_url",
        "object_doc_url",
        "hostinger_doc_url",
        "hostinger_doc_path",
        "document_urls",
        "display_location_city",
        "display_location_state",
        "display_quantity_summary",
        "ai_buyer_summary",
        "ai_clean_heading",
    ):
        if disc.get(fld) not in (None, ""):
            shell[fld] = disc[fld]
        elif rec.get(fld) not in (None, ""):
            shell[fld] = rec[fld]
    # Prefer CDN doc from ledger when present
    from scraper.pipeline_ledger import media_doc_path, media_doc_url

    url = media_doc_url(item)
    path = media_doc_path(item)
    if url:
        shell["object_doc_url"] = url
        shell["hostinger_doc_url"] = url
        shell["pdf_url"] = url
    if path:
        shell["hostinger_doc_path"] = path
    return shell


def build_archive_export(
    *,
    live_export: dict[str, Any],
    stripped_dropped: list[dict[str, Any]],
    ledger_items: list[Any],
    discovery_by_key: dict[str, dict[str, Any]],
    parsed_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build T-N archive export: stripped live rows + under-runway ledger shells."""
    from scraper.filters import is_archive_eligible
    from scraper.parse_cache import load_parse_artifact

    current = now or datetime.now(IST)
    live_keys = {stable_listing_key(a) for a in (live_export.get("auctions") or [])}
    by_key: dict[str, dict[str, Any]] = {}

    def _put(auction: dict[str, Any], *, reason: str | None = None) -> None:
        annotated = annotate_archive_auction(auction, now=current, reason=reason)
        if not annotated:
            return
        key = stable_listing_key(annotated)
        if key in live_keys:
            return
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = annotated
            return
        # Prefer richer catalogue when merging duplicates.
        if _catalogue_status(annotated) == "ready" and _catalogue_status(existing) != "ready":
            by_key[key] = annotated
        elif not (existing.get("lots") or []) and (annotated.get("lots") or []):
            by_key[key] = annotated

    for drop in stripped_dropped or []:
        auction = drop.get("auction") if isinstance(drop, dict) else None
        if isinstance(auction, dict):
            _put(auction, reason="aged_out")

    for item in ledger_items or []:
        key = getattr(item, "stable_key", None)
        if not key:
            continue
        closing = _parse_closing(getattr(item, "closing", None))
        if closing is None or not is_archive_eligible(closing, now=current):
            continue
        if key in live_keys or key in by_key:
            # Upgrade catalogue if we have parse later
            pass
        disc = discovery_by_key.get(key) or {}
        parsed_rec = None
        if parsed_root is not None:
            path = parsed_root / item.source / f"{item.source_auction_id}.json"
            art = load_parse_artifact(path) if path.is_file() else None
            if art and isinstance(art.get("record"), dict):
                parsed_rec = art["record"]
        shell = shell_from_ledger_item(item, discovery=disc, parsed_record=parsed_rec)
        reason = "closed" if closing < current else "under_runway"
        _put(shell, reason=reason)

    auctions = sorted(by_key.values(), key=lambda a: str(a.get("closing") or ""), reverse=True)
    return {
        "generated_at": current.isoformat(),
        "count": len(auctions),
        "auctions": auctions,
        "stats": {
            "archive": True,
            "retention_days": __import__("scraper.config", fromlist=["ARCHIVE_RETENTION_DAYS"]).ARCHIVE_RETENTION_DAYS,
            "by_reason": dict(
                Counter(str(a.get("archive_reason") or "unknown") for a in auctions)
            ),
            "catalogue_ready": sum(1 for a in auctions if a.get("catalogue_status") == "ready"),
        },
        "schema_version": 1,
    }
