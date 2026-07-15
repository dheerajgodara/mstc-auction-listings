"""Hostinger auction_quarantine.json — temporary skip list for stubborn gate edge cases."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from scraper.pipeline_markers import pull_pipeline_json, push_pipeline_json

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.auction_quarantine")

QUARANTINE_FILE = "auction_quarantine.json"
DEFAULT_AUTO_HOURS = 48
MAX_MANUAL_HOURS = 24 * 7  # 7 days


def _now() -> datetime:
    return datetime.now(IST)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except Exception:
        return None


def empty_quarantine() -> dict[str, Any]:
    return {"entries": {}, "updated_at": _now().isoformat()}


def load_quarantine(*, pull_remote: bool = True) -> dict[str, Any]:
    data: dict[str, Any] | None = None
    if pull_remote:
        data = pull_pipeline_json(QUARANTINE_FILE)
    if not data or not isinstance(data.get("entries"), dict):
        return empty_quarantine()
    return data


def save_quarantine(data: dict[str, Any], *, push_remote: bool = True) -> bool:
    payload = dict(data)
    payload["updated_at"] = _now().isoformat()
    if "entries" not in payload or not isinstance(payload["entries"], dict):
        payload["entries"] = {}
    if not push_remote:
        return True
    return push_pipeline_json(QUARANTINE_FILE, payload)


def prune_expired(data: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = now or _now()
    entries = dict(data.get("entries") or {})
    kept: dict[str, Any] = {}
    for key, meta in entries.items():
        if not isinstance(meta, dict):
            continue
        expires = _parse_iso(meta.get("expires_at"))
        if expires is None or expires <= current:
            continue
        kept[key] = meta
    out = dict(data)
    out["entries"] = kept
    return out


def active_quarantine_keys(
    data: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
    pull_remote: bool = True,
) -> set[str]:
    q = prune_expired(data or load_quarantine(pull_remote=pull_remote), now=now)
    return set(q.get("entries") or {})


def add_quarantine_entries(
    keys: list[str] | set[str],
    *,
    reason: str,
    source: str = "manual",
    hours: int | None = None,
    data: dict[str, Any] | None = None,
    push_remote: bool = True,
) -> dict[str, Any]:
    q = prune_expired(data or load_quarantine(pull_remote=push_remote))
    if hours is None:
        hours = DEFAULT_AUTO_HOURS if source.startswith("drain") or source == "auto" else MAX_MANUAL_HOURS
    hours = max(1, min(int(hours), MAX_MANUAL_HOURS))
    now = _now()
    expires = now + timedelta(hours=hours)
    entries = dict(q.get("entries") or {})
    for key in keys:
        k = str(key).strip()
        if not k:
            continue
        entries[k] = {
            "reason": reason,
            "added_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "source": source,
        }
    q["entries"] = entries
    save_quarantine(q, push_remote=push_remote)
    return q


def remove_quarantine_entries(
    keys: list[str] | set[str],
    *,
    data: dict[str, Any] | None = None,
    push_remote: bool = True,
) -> dict[str, Any]:
    q = prune_expired(data or load_quarantine(pull_remote=push_remote))
    entries = dict(q.get("entries") or {})
    for key in keys:
        entries.pop(str(key).strip(), None)
    q["entries"] = entries
    save_quarantine(q, push_remote=push_remote)
    return q


def list_quarantine(*, pull_remote: bool = True) -> dict[str, Any]:
    return prune_expired(load_quarantine(pull_remote=pull_remote))
