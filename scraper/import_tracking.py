from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
HISTORY_MAX_DAYS = 90
logger = logging.getLogger("scraper.import_tracking")


def stable_auction_key(record: dict[str, Any]) -> str:
    source = record.get("source") or "mstc"
    sid = record.get("source_auction_id") or record.get("id")
    return f"{source}:{sid}"


def parse_iso_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(IST) if value.tzinfo else value.replace(tzinfo=IST)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(IST)
    except (TypeError, ValueError):
        return None


def _index_previous_auctions(previous: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not previous:
        return {}
    return {stable_auction_key(a): a for a in previous.get("auctions", [])}


def apply_first_seen_tracking(
    auctions: list[dict[str, Any]],
    *,
    previous_export: dict[str, Any] | None,
    automation_ran_at: datetime,
    generated_at: datetime | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Stamp first_seen_at / imported_at / last_seen_at on each auction record."""
    generated_at = generated_at or automation_ran_at
    prev_idx = _index_previous_auctions(previous_export)
    prev_generated = parse_iso_datetime(previous_export.get("generated_at") if previous_export else None)
    backfill_ts = prev_generated or generated_at

    current_keys: set[str] = set()
    new_count = 0

    for auction in auctions:
        key = stable_auction_key(auction)
        current_keys.add(key)
        prev = prev_idx.get(key)

        prev_first = None
        if prev:
            prev_first = parse_iso_datetime(prev.get("first_seen_at") or prev.get("imported_at"))

        if prev_first is not None:
            first_seen = prev_first
        elif prev is not None:
            first_seen = backfill_ts
        else:
            first_seen = automation_ran_at
            new_count += 1

        auction["first_seen_at"] = first_seen.isoformat()
        auction["imported_at"] = first_seen.isoformat()
        auction["last_seen_at"] = automation_ran_at.isoformat()

    removed_count = 0
    if previous_export:
        prev_keys = {stable_auction_key(a) for a in previous_export.get("auctions", [])}
        removed_count = len(prev_keys - current_keys)

    return auctions, new_count, removed_count


def build_source_metadata(
    auctions: list[dict[str, Any]],
    stats: dict[str, Any] | None,
    *,
    batch_manifest_summary: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    by_source = Counter(a.get("source") or "mstc" for a in auctions)
    lots_by: Counter[str] = Counter()
    for auction in auctions:
        src = auction.get("source") or "mstc"
        lots_by[src] += len(auction.get("lots") or [])

    batch_status: dict[str, str] = {}
    if batch_manifest_summary:
        for batch in batch_manifest_summary:
            src = str(batch.get("source") or "unknown")
            status = str(batch.get("status") or "unknown")
            if status == "failed":
                batch_status[src] = "failed"
            elif src not in batch_status and status == "done":
                batch_status[src] = "success"

    documents = (stats or {}).get("documents") or {}
    sources: dict[str, dict[str, Any]] = {}
    for src in ("mstc", "gem_forward", "eauction"):
        count = int(by_source.get(src, 0))
        if batch_status.get(src) == "failed":
            status = "failed"
        elif count > 0:
            status = "success"
        else:
            status = "missing"
        sources[src] = {
            "count": count,
            "lots": int(lots_by.get(src, 0)),
            "status": status,
            "documents_downloaded": int(documents.get("downloaded", 0) or 0) if src == "mstc" else None,
            "documents_failed": int(documents.get("failed", 0) or 0) if src == "mstc" else None,
        }
    return sources


def build_daily_import_entry(
    *,
    automation_ran_at: datetime,
    run_id: str,
    count: int,
    total_lots: int,
    by_source: dict[str, int],
    new_count: int,
    removed_count: int,
    status: str = "success",
) -> dict[str, Any]:
    return {
        "date": automation_ran_at.astimezone(IST).date().isoformat(),
        "run_id": run_id,
        "automation_ran_at": automation_ran_at.isoformat(),
        "mstc_auctions": int(by_source.get("mstc", 0)),
        "gem_forward_auctions": int(by_source.get("gem_forward", 0)),
        "eauction_auctions": int(by_source.get("eauction", 0)),
        "total_auctions": count,
        "total_lots": total_lots,
        "new_auctions_first_seen": new_count,
        "removed_auctions": removed_count,
        "status": status,
    }


def merge_import_history(
    existing: list[dict[str, Any]],
    entry: dict[str, Any],
    *,
    max_days: int = HISTORY_MAX_DAYS,
) -> list[dict[str, Any]]:
    run_id = entry.get("run_id")
    history = [h for h in existing if h.get("run_id") != run_id]
    history.append(entry)
    history.sort(key=lambda h: h.get("automation_ran_at") or h.get("date") or "")

    cutoff_ord = datetime.now(IST).date().toordinal() - max_days
    trimmed: list[dict[str, Any]] = []
    for row in history:
        raw_date = str(row.get("date") or row.get("automation_ran_at") or "")[:10]
        try:
            day_ord = date.fromisoformat(raw_date).toordinal()
        except ValueError:
            day_ord = 0
        if day_ord >= cutoff_ord:
            trimmed.append(row)
    return trimmed


def load_import_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, list):
        return raw
    return list(raw.get("entries") or [])


def save_import_history(path: Path, history: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def finalize_export_payload(
    data: dict[str, Any],
    *,
    previous_export: dict[str, Any] | None,
    automation_ran_at: datetime | None = None,
    run_id: str | None = None,
    history_path: Path | None = None,
    status: str = "success",
) -> dict[str, Any]:
    """Add run metadata and per-auction import timestamps to an export dict."""
    now = datetime.now(IST)
    automation_ran_at = automation_ran_at or parse_iso_datetime(data.get("automation_ran_at")) or now
    generated_at = parse_iso_datetime(data.get("generated_at")) or now

    auctions = list(data.get("auctions") or [])
    updated, new_count, removed_count = apply_first_seen_tracking(
        auctions,
        previous_export=previous_export,
        automation_ran_at=automation_ran_at,
        generated_at=generated_at,
    )

    stats = data.get("stats") or {}
    total_lots = sum(len(a.get("lots") or []) for a in updated)
    by_source = dict(Counter(a.get("source") or "mstc" for a in updated))
    batch_summary = stats.get("batch_manifest_summary")
    sources = build_source_metadata(updated, stats, batch_manifest_summary=batch_summary)

    run_id = run_id or data.get("run_id") or f"finalize_{automation_ran_at.strftime('%Y%m%d_%H%M%S')}"
    daily_entry = build_daily_import_entry(
        automation_ran_at=automation_ran_at,
        run_id=run_id,
        count=len(updated),
        total_lots=total_lots,
        by_source=by_source,
        new_count=new_count,
        removed_count=removed_count,
        status=status,
    )

    existing_history = load_import_history(history_path) if history_path else list(data.get("daily_import_summary") or [])
    history = merge_import_history(existing_history, daily_entry)
    if history_path:
        save_import_history(history_path, history)

    data["auctions"] = updated
    data["count"] = len(updated)
    data["generated_at"] = generated_at.isoformat()
    data["export_generated_at"] = generated_at.isoformat()
    data["automation_ran_at"] = automation_ran_at.isoformat()
    data["run_id"] = run_id
    data["sources"] = sources
    data["daily_import_summary"] = history
    stats = dict(stats)
    stats["import_tracking"] = {
        "new_auctions": new_count,
        "removed_auctions": removed_count,
        "previous_count": len(previous_export.get("auctions", [])) if previous_export else 0,
    }
    stats["total_lots_in_export"] = total_lots
    data["stats"] = stats
    return data
