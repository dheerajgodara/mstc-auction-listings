"""Input hash, cache, checkpoint, and resumable enrichment queue."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from scraper.ai_enrichment.payload import build_enrichment_prompt, payload_stats
from scraper.ai_enrichment.provider import EnrichmentProvider, get_provider
from scraper.ai_enrichment.schema import (
    AI_SCHEMA_VERSION,
    PROMPT_VERSION,
    listing_confidence,
    validate_listing_enrichment,
)
from scraper.config import AI_ENRICHMENT_CACHE_DIR
from scraper.display_enrichment import apply_display_enrichment
from scraper.models import AuctionRecord

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
FATAL_PROVIDER_ERRORS = {"openrouter_auth_failed", "openrouter_api_key_missing"}
DEFAULT_DAILY_AI_CALL_BUDGET = 950


@dataclass
class EnrichmentRunReport:
    processed: int = 0
    ready: int = 0
    skipped: int = 0
    rejected: int = 0
    failed: int = 0
    dry_run: bool = False
    mock: bool = False
    no_network: bool = True
    allow_network: bool = False
    network_safe: bool = True
    will_call_provider: bool = False
    prompt_version: str = PROMPT_VERSION
    schema_version: str = AI_SCHEMA_VERSION
    dry_run_estimate: Optional[dict[str, Any]] = None
    selection: Optional[dict[str, Any]] = None
    budget: Optional[dict[str, Any]] = None
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "processed": self.processed,
            "ready": self.ready,
            "skipped": self.skipped,
            "rejected": self.rejected,
            "failed": self.failed,
            "dry_run": self.dry_run,
            "mock": self.mock,
            "no_network": self.no_network,
            "allow_network": self.allow_network,
            "network_safe": self.network_safe,
            "will_call_provider": self.will_call_provider,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "details": self.details,
        }
        if self.dry_run_estimate is not None:
            payload["dry_run_estimate"] = self.dry_run_estimate
        if self.selection is not None:
            payload["selection"] = self.selection
        if self.budget is not None:
            payload["budget"] = self.budget
        return payload


def _ledger_path(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> Path:
    return cache_dir / "_daily_usage.json"


def _done_registry_path(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> Path:
    return cache_dir / "_done_registry.json"


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()


def read_daily_usage(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> dict[str, Any]:
    path = _ledger_path(cache_dir)
    if not path.is_file():
        return {"date": _today_ist(), "attempted": 0, "ready": 0, "rejected": 0, "failed": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"date": _today_ist(), "attempted": 0, "ready": 0, "rejected": 0, "failed": 0}
    if payload.get("date") != _today_ist():
        return {"date": _today_ist(), "attempted": 0, "ready": 0, "rejected": 0, "failed": 0}
    return {
        "date": payload.get("date") or _today_ist(),
        "attempted": int(payload.get("attempted", 0) or 0),
        "ready": int(payload.get("ready", 0) or 0),
        "rejected": int(payload.get("rejected", 0) or 0),
        "failed": int(payload.get("failed", 0) or 0),
    }


def write_daily_usage(payload: dict[str, Any], cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _ledger_path(cache_dir).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_done_registry(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> dict[str, Any]:
    path = _done_registry_path(cache_dir)
    if not path.is_file():
        return {"version": 1, "items": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "items": {}}
    items = payload.get("items")
    if not isinstance(items, dict):
        items = {}
    return {"version": int(payload.get("version", 1) or 1), "items": items}


def write_done_registry(payload: dict[str, Any], cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _done_registry_path(cache_dir).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _auction_registry_keys(record: AuctionRecord | str) -> list[str]:
    if isinstance(record, str):
        return [record]
    keys = [record.id]
    if record.source and record.source_auction_id:
        keys.append(f"{record.source}:{record.source_auction_id}")
    if record.auction_number:
        keys.append(record.auction_number)
    return list(dict.fromkeys(k for k in keys if k))


def done_registry_entry(record: AuctionRecord, cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> Optional[dict[str, Any]]:
    items = read_done_registry(cache_dir).get("items") or {}
    for key in _auction_registry_keys(record):
        entry = items.get(key)
        if isinstance(entry, dict) and entry.get("status") == "ready":
            return entry
    return None


def is_ai_done(record: AuctionRecord, cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> bool:
    return read_done_cache(record, cache_dir) is not None


def mark_ai_done(
    record: AuctionRecord,
    *,
    input_hash: str,
    cache_path: Path,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
    model: Optional[str] = None,
    confidence: Optional[str] = None,
) -> None:
    registry = read_done_registry(cache_dir)
    items = registry.setdefault("items", {})
    now = datetime.now(IST).isoformat()
    primary_key = record.id
    entry = {
        "auction_id": record.id,
        "source": record.source,
        "source_auction_id": record.source_auction_id,
        "auction_number": record.auction_number,
        "status": "ready",
        "input_hash": input_hash,
        "cache_file": cache_path.name,
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "model": model,
        "confidence": confidence,
        "done_at": now,
        "primary_key": primary_key,
    }
    items[primary_key] = entry
    for alias in _auction_registry_keys(record):
        if alias != primary_key:
            items[alias] = {"status": "ready", "primary_key": primary_key}
    write_done_registry(registry, cache_dir)


def read_done_cache(record: AuctionRecord, cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> Optional[dict[str, Any]]:
    registry = read_done_registry(cache_dir)
    items = registry.get("items") or {}
    entry = done_registry_entry(record, cache_dir)
    if not entry:
        return None
    primary_key = entry.get("primary_key") or record.id
    primary_entry = items.get(primary_key, entry)
    cache_file = primary_entry.get("cache_file") if isinstance(primary_entry, dict) else None
    if not cache_file:
        return None
    path = cache_dir / str(cache_file)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("status") != "ready":
        return None
    return payload


def daily_budget_state(
    *,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
    daily_budget: int = DEFAULT_DAILY_AI_CALL_BUDGET,
) -> dict[str, Any]:
    usage = read_daily_usage(cache_dir)
    remaining = max(0, int(daily_budget) - int(usage.get("attempted", 0)))
    return {
        "daily_budget": int(daily_budget),
        "date": usage.get("date"),
        "attempted_today": usage.get("attempted", 0),
        "ready_today": usage.get("ready", 0),
        "rejected_today": usage.get("rejected", 0),
        "failed_today": usage.get("failed", 0),
        "remaining_today": remaining,
    }


HIGH_VALUE_MATERIALS = {
    "transmission_scrap",
    "aluminium_conductor",
    "ferrous_scrap",
    "cable_scrap",
    "machinery",
    "vehicle_lot",
    "coal",
    "minerals",
}


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _has_current_cache(record: AuctionRecord, cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> bool:
    input_hash = compute_input_hash(record)
    cached = read_cache(record.id, input_hash, cache_dir)
    if cached and cache_is_current(cached, input_hash):
        mark_ai_done(
            record,
            input_hash=input_hash,
            cache_path=_cache_path(record.id, input_hash, cache_dir),
            cache_dir=cache_dir,
            model=cached.get("model"),
            confidence=cached.get("confidence"),
        )
        return True
    return False


def ai_priority(record: AuctionRecord, cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> dict[str, Any]:
    """Return deterministic priority score and reasons for AI enrichment selection."""
    record = apply_display_enrichment(record)
    score = 0
    reasons: list[str] = []

    if is_ai_done(record, cache_dir):
        return {"score": -1, "reasons": ["ai_done_registry"], "eligible": False}

    if _has_current_cache(record, cache_dir):
        return {"score": -1, "reasons": ["current_ai_cache"], "eligible": False}

    score += 1000
    reasons.append("missing_or_stale_ai_cache")

    qty = record.display_total_quantity_mt or 0
    if qty >= 1000:
        score += 320
        reasons.append("1000_mt_plus")
    elif qty >= 500:
        score += 260
        reasons.append("500_mt_plus")
    elif qty >= 100:
        score += 200
        reasons.append("100_mt_plus")
    elif qty >= 50:
        score += 140
        reasons.append("50_mt_plus")
    elif qty >= 10:
        score += 90
        reasons.append("10_mt_plus")

    material = (record.display_material_category or record.asset_category or "").strip()
    if material in HIGH_VALUE_MATERIALS:
        score += 150
        reasons.append(f"high_value_material:{material}")

    lot_count = len(record.lots)
    if lot_count >= 20:
        score += 120
        reasons.append("20_plus_lots")
    elif lot_count >= 5:
        score += 70
        reasons.append("5_plus_lots")

    has_docs = any(lot.documents for lot in record.lots)
    has_photos = any(lot.preview_images or lot.photo_file for lot in record.lots)
    if has_docs:
        score += 45
        reasons.append("documents_available")
    if has_photos:
        score += 35
        reasons.append("photos_available")

    closing = _parse_dt(record.closing)
    if closing:
        now = datetime.now(IST)
        if closing.tzinfo is None:
            closing = closing.replace(tzinfo=IST)
        hours = (closing.astimezone(IST) - now).total_seconds() / 3600
        if 0 <= hours <= 72:
            score += 85
            reasons.append("closing_within_72h")
        elif 0 <= hours <= 168:
            score += 45
            reasons.append("closing_within_7d")

    title = (record.display_title or record.item_summary or "").strip()
    if not title or len(title) > 110 or title.lower().startswith(("bids are invited", "sale of")):
        score += 60
        reasons.append("weak_title")

    if record.source == "mstc":
        score += 25
        reasons.append("rich_mstc_catalogue")

    imported = _parse_dt(record.imported_at or record.first_seen_at)
    if imported:
        now = datetime.now(IST)
        if imported.tzinfo is None:
            imported = imported.replace(tzinfo=IST)
        days = (now - imported.astimezone(IST)).total_seconds() / 86400
        if 0 <= days <= 2:
            score += 30
            reasons.append("recently_imported")

    return {
        "score": score,
        "reasons": reasons[:8],
        "eligible": True,
        "quantity_mt": qty,
        "lot_count": lot_count,
        "material": material or None,
        "source": record.source,
    }


def select_priority_auctions(
    auctions: list[AuctionRecord],
    *,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
    limit: Optional[int] = None,
) -> tuple[list[tuple[AuctionRecord, dict[str, Any]]], dict[str, Any]]:
    scored: list[tuple[AuctionRecord, dict[str, Any]]] = []
    skipped_current = 0
    skipped_done = 0
    for record in auctions:
        priority = ai_priority(record, cache_dir)
        if not priority.get("eligible"):
            if "ai_done_registry" in (priority.get("reasons") or []):
                skipped_done += 1
            else:
                skipped_current += 1
            continue
        scored.append((record, priority))
    scored.sort(
        key=lambda item: (
            item[1]["score"],
            item[1].get("quantity_mt") or 0,
            len(item[0].lots),
            item[0].id,
        ),
        reverse=True,
    )
    selected = scored[:limit] if limit is not None else scored
    reason_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for _record, priority in selected:
        source = str(priority.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
        for reason in priority.get("reasons") or []:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    summary = {
        "eligible": len(scored),
        "selected": len(selected),
        "remaining_after_selection": max(0, len(scored) - len(selected)),
        "estimated_runs_to_clear": (
            0
            if not selected
            else (max(0, len(scored) - len(selected)) + max(1, len(selected)) - 1) // max(1, len(selected))
        ),
        "current_cache_skipped": skipped_current,
        "already_ai_done": skipped_done,
        "priority_reason_counts": reason_counts,
        "selected_by_source": source_counts,
        "top_selected": [
            {
                "auction_id": record.id,
                "score": priority.get("score"),
                "reasons": priority.get("reasons"),
                "quantity_mt": priority.get("quantity_mt"),
                "lot_count": priority.get("lot_count"),
                "source": priority.get("source"),
            }
            for record, priority in selected[:10]
        ],
    }
    return selected, summary


def compute_input_hash(record: AuctionRecord) -> str:
    enriched = apply_display_enrichment(record)
    parts: list[str] = [
        PROMPT_VERSION,
        AI_SCHEMA_VERSION,
        record.id,
        record.source,
        record.auction_number or "",
        record.item_summary or "",
        record.location or "",
        record.state or "",
        enriched.display_title or "",
        enriched.display_material_category or "",
        str(len(record.lots)),
    ]
    for lot in record.lots:
        parts.extend(
            [
                lot.lot_id,
                lot.item_title or "",
                lot.item_description or "",
                lot.quantity or "",
                lot.unit or "",
            ]
        )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _cache_path(
    auction_id: str,
    input_hash: str,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in auction_id)[:120]
    return cache_dir / f"{safe_id}_{input_hash}_{PROMPT_VERSION}.json"


def read_cache(
    auction_id: str,
    input_hash: str,
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
) -> Optional[dict[str, Any]]:
    path = _cache_path(auction_id, input_hash, cache_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache(
    auction_id: str,
    input_hash: str,
    payload: dict[str, Any],
    cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
) -> Path:
    path = _cache_path(auction_id, input_hash, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def cache_is_current(cached: dict[str, Any], input_hash: str) -> bool:
    return (
        cached.get("input_hash") == input_hash
        and cached.get("prompt_version") == PROMPT_VERSION
        and cached.get("schema_version") == AI_SCHEMA_VERSION
        and cached.get("status") == "ready"
    )


def build_cached_enrichment(record: AuctionRecord, output_dict: dict[str, Any]) -> dict[str, Any]:
    input_hash = compute_input_hash(record)
    now = datetime.now(IST).isoformat()
    return {
        "auction_id": record.id,
        "input_hash": input_hash,
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "status": output_dict.get("status", "ready"),
        "model": output_dict.get("model"),
        "generated_at": output_dict.get("generated_at") or now,
        "confidence": output_dict.get("confidence"),
        "rejection_reasons": output_dict.get("rejection_reasons") or [],
        "listing": output_dict.get("listing"),
        "lots": output_dict.get("lots") or [],
    }


class EnrichmentQueue:
    def __init__(
        self,
        *,
        provider: Optional[EnrichmentProvider] = None,
        cache_dir: Path = AI_ENRICHMENT_CACHE_DIR,
        dry_run: bool = False,
        mock: bool = False,
        no_network: bool = True,
        allow_network: bool = False,
        max_requests: Optional[int] = None,
        daily_budget: int = DEFAULT_DAILY_AI_CALL_BUDGET,
    ) -> None:
        self.cache_dir = cache_dir
        self.dry_run = dry_run
        self.mock = mock
        self.no_network = no_network
        self.allow_network = allow_network
        self.max_requests = max_requests
        self.daily_budget = daily_budget
        self.provider = provider or get_provider(mock=mock, allow_network=allow_network)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._requests = 0
        self._daily_usage = read_daily_usage(self.cache_dir)

    def _should_stop(self) -> bool:
        if self.max_requests is not None and self._requests >= self.max_requests:
            return True
        return int(self._daily_usage.get("attempted", 0) or 0) >= self.daily_budget

    def _record_attempt_result(self, status: str) -> None:
        self._daily_usage["attempted"] = int(self._daily_usage.get("attempted", 0) or 0) + 1
        if status in {"ready", "rejected", "failed"}:
            self._daily_usage[status] = int(self._daily_usage.get(status, 0) or 0) + 1
        write_daily_usage(self._daily_usage, self.cache_dir)

    def process_auction(self, record: AuctionRecord) -> dict[str, Any]:
        input_hash = compute_input_hash(record)
        if is_ai_done(record, self.cache_dir):
            return {"auction_id": record.id, "status": "skipped", "reason": "ai_done_registry"}

        cached = read_cache(record.id, input_hash, self.cache_dir)
        if cached and cache_is_current(cached, input_hash):
            cache_path = _cache_path(record.id, input_hash, self.cache_dir)
            mark_ai_done(
                record,
                input_hash=input_hash,
                cache_path=cache_path,
                cache_dir=self.cache_dir,
                model=cached.get("model"),
                confidence=cached.get("confidence"),
            )
            return {"auction_id": record.id, "status": "skipped", "reason": "cache_hit"}

        if self.dry_run:
            prompt, payload = build_enrichment_prompt(record)
            stats = payload_stats(payload)
            return {
                "auction_id": record.id,
                "status": "dry_run",
                "input_hash": input_hash,
                "payload_stats": stats,
                "prompt_chars": len(prompt),
            }

        if cached and cached.get("status") == "ready" and cached.get("input_hash") == input_hash:
            return {"auction_id": record.id, "status": "skipped", "reason": "cache_hit"}

        if self._should_stop():
            reason = "daily_budget_exhausted"
            if self.max_requests is not None and self._requests >= self.max_requests:
                reason = "max_requests"
            return {"auction_id": record.id, "status": "skipped", "reason": reason}

        self._requests += 1
        record = apply_display_enrichment(record)
        prompt, _payload = build_enrichment_prompt(record)
        expected_lot_ids = {lot.lot_id for lot in record.lots}

        raw, model = self.provider.enrich_listing(record, prompt)
        if not raw:
            reason = getattr(self.provider, "last_error", None) or "provider_empty"
            if reason in FATAL_PROVIDER_ERRORS:
                self._record_attempt_result("failed")
                return {"auction_id": record.id, "status": "failed", "reason": reason, "fatal": True}
            failure = {
                "auction_id": record.id,
                "input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
                "schema_version": AI_SCHEMA_VERSION,
                "status": "failed",
                "generated_at": datetime.now(IST).isoformat(),
            }
            write_cache(record.id, input_hash, failure, self.cache_dir)
            self._record_attempt_result("failed")
            return {"auction_id": record.id, "status": "failed", "reason": reason}

        validation = validate_listing_enrichment(raw, expected_lot_ids=expected_lot_ids)
        if not validation.ok or validation.output is None:
            rejected = {
                "auction_id": record.id,
                "input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
                "schema_version": AI_SCHEMA_VERSION,
                "status": "rejected",
                "model": model,
                "generated_at": datetime.now(IST).isoformat(),
                "rejection_reasons": validation.rejection_reasons,
                "unknown_tags": validation.unknown_tags,
            }
            write_cache(record.id, input_hash, rejected, self.cache_dir)
            self._record_attempt_result("rejected")
            return {
                "auction_id": record.id,
                "status": "rejected",
                "reasons": validation.rejection_reasons,
            }

        output = validation.output
        confidence = listing_confidence(output)
        ready_payload = {
            "auction_id": record.id,
            "input_hash": input_hash,
            "prompt_version": PROMPT_VERSION,
            "schema_version": AI_SCHEMA_VERSION,
            "status": "ready",
            "model": model,
            "generated_at": datetime.now(IST).isoformat(),
            "confidence": confidence,
            "rejection_reasons": [],
            "listing": output.model_dump(),
            "lots": [lot.model_dump() for lot in output.lots],
        }
        cache_path = write_cache(record.id, input_hash, ready_payload, self.cache_dir)
        mark_ai_done(
            record,
            input_hash=input_hash,
            cache_path=cache_path,
            cache_dir=self.cache_dir,
            model=model,
            confidence=confidence,
        )
        self._record_attempt_result("ready")
        return {"auction_id": record.id, "status": "ready", "confidence": confidence, "model": model}

    def run(
        self,
        auctions: list[AuctionRecord],
        *,
        auction_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> EnrichmentRunReport:
        network_safe = self.dry_run or not self.allow_network
        report = EnrichmentRunReport(
            dry_run=self.dry_run,
            mock=self.mock,
            no_network=self.no_network,
            allow_network=self.allow_network,
            network_safe=network_safe,
            will_call_provider=not self.dry_run and self.allow_network and not self.mock,
        )
        report.budget = daily_budget_state(cache_dir=self.cache_dir, daily_budget=self.daily_budget)
        effective_limit = limit
        if not self.dry_run:
            remaining_today = int(report.budget.get("remaining_today", 0) or 0)
            if effective_limit is None:
                effective_limit = remaining_today
            else:
                effective_limit = min(int(effective_limit), remaining_today)
        selected_pairs: list[tuple[AuctionRecord, dict[str, Any]]]
        selection_summary: dict[str, Any]
        if auction_id:
            selected = [a for a in auctions if a.id == auction_id or a.auction_number == auction_id]
            selected_pairs = [(record, ai_priority(record, self.cache_dir)) for record in selected]
            selection_summary = {
                "eligible": len(selected_pairs),
                "selected": len(selected_pairs),
                "current_cache_skipped": 0,
                "priority_reason_counts": {},
                "selected_by_source": {},
                "top_selected": [],
                "auction_id_filter": auction_id,
            }
        else:
            selected_pairs, selection_summary = select_priority_auctions(
                auctions,
                cache_dir=self.cache_dir,
                limit=effective_limit,
            )
        report.selection = selection_summary

        prompt_char_counts: list[int] = []
        for record, priority in selected_pairs:
            if self._should_stop() and not self.dry_run:
                break
            detail = self.process_auction(record)
            detail["priority_score"] = priority.get("score")
            detail["priority_reasons"] = priority.get("reasons") or []
            report.details.append(detail)
            report.processed += 1
            status = detail.get("status")
            if status == "ready":
                report.ready += 1
            elif status == "skipped":
                report.skipped += 1
            elif status == "rejected":
                report.rejected += 1
            elif status == "failed":
                report.failed += 1
                if detail.get("fatal"):
                    break
            elif status == "dry_run":
                report.skipped += 1
                prompt_chars = detail.get("prompt_chars")
                if isinstance(prompt_chars, int):
                    prompt_char_counts.append(prompt_chars)

        if self.dry_run and prompt_char_counts:
            total = sum(prompt_char_counts)
            report.dry_run_estimate = {
                "processed": len(prompt_char_counts),
                "total_prompt_chars": total,
                "average_prompt_chars": round(total / len(prompt_char_counts), 1),
                "max_prompt_chars": max(prompt_char_counts),
            }
        report.budget = daily_budget_state(cache_dir=self.cache_dir, daily_budget=self.daily_budget)
        return report


def count_cache_stats(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> dict[str, int]:
    stats = {"ready": 0, "failed": 0, "rejected": 0, "other": 0, "total": 0}
    if not cache_dir.is_dir():
        return stats
    for path in cache_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        stats["total"] += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            status = payload.get("status", "other")
            if status in stats:
                stats[status] += 1
            else:
                stats["other"] += 1
        except Exception:
            stats["other"] += 1
    return stats
