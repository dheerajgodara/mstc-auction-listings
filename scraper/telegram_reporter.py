"""Compact Telegram status for Scrap Auction India pipelines.

Design rules (keep messages scannable on mobile):
- Title line: emoji + system + outcome (≤ ~40 chars)
- 1–3 body lines of facts only
- Optional single GitHub link
- Soft limit ~450 chars; never dump run_id/timestamps/section dumps
- Quiet events (started/selection/cycle) are not sent
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from typing import Any

logger = logging.getLogger("scraper.telegram_reporter")

# Intermediate noise — callers may still invoke send_telegram_report; we no-op.
QUIET_EVENTS: frozenset[str] = frozenset(
    {
        "started",
        "comparison_done",
        "deep_scrape_done",
        "download_started",
        "download_selection",
        "parse_started",
        "parse_selection",
        "deploy_started",
        "drain_started",
        "drain_cycle",
        "selection_done",  # AI
    }
)

MAX_MESSAGE_CHARS = 450


def _credentials() -> tuple[str, str] | None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return None
    return token, chat_id


def _h(value: object) -> str:
    return escape(str(value), quote=False)


def _fmt_duration(seconds: object) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return ""
    if value < 60:
        return f"{value:.0f}s"
    minutes = int(value // 60)
    secs = int(round(value % 60))
    if minutes < 60:
        return f"{minutes}m" if secs == 0 else f"{minutes}m {secs}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes}m"


def _clip(text: str, max_chars: int = 160) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def _run_link(payload: dict[str, Any]) -> str:
    url = str(payload.get("github_run_url") or "").strip()
    if not url:
        return ""
    return f'<a href="{escape(url, quote=True)}">log</a>'


def _ledger_bits(ledger: dict[str, Any] | None) -> str:
    if not ledger:
        return ""
    dl = ledger.get("download")
    parse = ledger.get("parse")
    parts: list[str] = []
    if isinstance(dl, dict) and dl:
        pending = int(dl.get("pending") or 0)
        done = int(dl.get("done") or 0)
        failed = int(dl.get("failed") or 0)
        parts.append(f"DL {done}✓ {pending}⏳" + (f" {failed}✗" if failed else ""))
    if isinstance(parse, dict) and parse:
        pending = int(parse.get("pending") or 0) + int(parse.get("failed") or 0)
        done = int(parse.get("done") or 0)
        parts.append(f"Parse {done}✓ {pending}⏳")
    ready = ledger.get("deploy_ready")
    if ready not in (None, "", 0):
        parts.append(f"Ready {ready}")
    return " · ".join(parts)


def _finish(lines: list[str], payload: dict[str, Any]) -> str:
    link = _run_link(payload)
    if link:
        lines.append(link)
    text = "\n".join(line for line in lines if line is not None and str(line).strip() != "")
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"
    return text


def _title(emoji: str, system: str, outcome: str) -> str:
    return f"<b>{_h(emoji)} {_h(system)} · {_h(outcome)}</b>"


def build_telegram_message(payload: dict[str, Any], *, event: str) -> str:
    """Build a short HTML Telegram message for pipeline / legacy refresh events."""
    pipeline = str(payload.get("pipeline") or "job")
    errors = payload.get("errors") or []
    err = _clip(errors[0] if errors else payload.get("error") or "", 140)

    # --- Download family ---
    if event == "download_done":
        ok = payload.get("download_ok", 0)
        fail = payload.get("download_failed", 0)
        dur = _fmt_duration(payload.get("wall_seconds"))
        line2 = f"{ok} ok · {fail} fail" + (f" · {dur}" if dur else "")
        return _finish(
            [_title("⬇️", "Download", "done"), line2, _ledger_bits(payload.get("ledger"))],
            payload,
        )
    if event == "download_failed":
        return _finish(
            [_title("❌", "Download", "failed"), err or "see log", _ledger_bits(payload.get("ledger"))],
            payload,
        )
    if event == "download_retry_scheduled":
        attempt = payload.get("retry_attempt") or "?"
        wait = payload.get("wait_minutes") or "?"
        return _finish(
            [_title("🔁", "Download", "retry"), f"attempt {attempt} · wait {wait}m"],
            payload,
        )
    if event == "download_retries_exhausted":
        return _finish(
            [_title("🛑", "Download", "retries done"), "waiting next 6h slot"],
            payload,
        )

    # --- Parse ---
    if event == "parse_done":
        ok = payload.get("parse_ok", 0)
        fail = payload.get("parse_failed", 0)
        auctions = payload.get("auctions")
        line2 = f"{ok} ok · {fail} fail"
        if auctions is not None:
            line2 += f" · export {auctions}"
        lines = [_title("🧩", "Parse", "done"), line2]
        note = str(payload.get("hygiene_note") or "").strip()
        if not note and int(payload.get("dropped_aged_out") or 0) > 0:
            n = int(payload.get("dropped_aged_out") or 0)
            note = f"dropped {n} aged-out"
        if note:
            lines.append(note)
        lines.append(_ledger_bits(payload.get("ledger")))
        return _finish(lines, payload)
    if event == "parse_failed":
        return _finish(
            [_title("❌", "Parse", "failed"), err or "see log", _ledger_bits(payload.get("ledger"))],
            payload,
        )
    if event == "quarantine_added":
        n = payload.get("quarantine_added") or "?"
        hours = payload.get("quarantine_hours") or 48
        return _finish(
            [_title("⚠️", "Quarantine", "added"), f"added {n} · {hours}h"],
            payload,
        )

    # --- Deploy ---
    if event == "deploy_done":
        if payload.get("deploy_skipped_unchanged"):
            outcome = "skipped (unchanged)"
        else:
            outcome = "done"
        n = payload.get("auctions")
        line2 = f"{n} auctions" if n is not None else "live updated"
        return _finish([_title("🚀", "Deploy", outcome), line2], payload)
    if event == "deploy_failed":
        return _finish([_title("❌", "Deploy", "failed"), err or "see log"], payload)

    # --- Drain ---
    if event == "drain_done":
        cycles = payload.get("cycles_completed", 0)
        left = payload.get("parse_backlog_end")
        line2 = f"{cycles} cycles"
        if left is not None:
            line2 += f" · parse left {left}"
        return _finish(
            [_title("✅", "Drain", "done"), line2, _ledger_bits(payload.get("ledger"))],
            payload,
        )
    if event == "drain_stopped":
        return _finish(
            [
                _title("🛑", "Drain", "stopped"),
                err or "see log",
                _ledger_bits(payload.get("ledger")),
            ],
            payload,
        )

    # --- Legacy refresh / UI deploy ---
    if event in {"success", "completed"}:
        n = payload.get("total_auctions") or payload.get("auctions")
        line2 = f"{n} auctions" if n is not None else "ok"
        by = payload.get("by_source") or {}
        if by:
            line2 += " · " + ", ".join(f"{k}={v}" for k, v in sorted(by.items())[:4])
        return _finish([_title("✅", "Refresh", "done"), line2], payload)
    if event in {"failed", "blocked"}:
        system = "Refresh" if pipeline != "deploy_ui" else "UI deploy"
        return _finish([_title("❌" if event == "failed" else "🚫", system, event), err or "see log"], payload)

    # Quiet / unknown: still return a tiny stub (may be unused when QUIET filters)
    return _finish([_title("ℹ️", pipeline.title(), event)], payload)


def build_ai_enrichment_message(payload: dict[str, Any], *, event: str = "report") -> str:
    """Short AI enrichment Telegram card."""
    if event == "started":
        return _finish([_title("🤖", "AI", "started")], payload)
    if event == "skipped":
        reason = _clip(payload.get("error") or payload.get("skip_reason") or "skipped", 120)
        return _finish([_title("⏭️", "AI", "skipped"), reason], payload)
    if event == "failed":
        return _finish(
            [_title("❌", "AI", "failed"), _clip(payload.get("error") or "see log", 140)],
            payload,
        )

    # complete / report
    ready = payload.get("ready", 0)
    failed = payload.get("failed", 0)
    skipped = payload.get("skipped", 0)
    processed = payload.get("processed", 0)
    budget = payload.get("budget") or {}
    selection = payload.get("selection") or {}
    line2 = f"{ready} ready · {failed} fail · {skipped} skip · {processed} ran"
    line3_parts: list[str] = []
    if budget:
        rem = budget.get("remaining_today")
        if rem is not None:
            line3_parts.append(f"budget left {rem}")
    rem_sel = selection.get("remaining_after_selection")
    if rem_sel is not None:
        line3_parts.append(f"queue {rem_sel}")
    dur = _fmt_duration(payload.get("duration_sec"))
    if dur:
        line3_parts.append(dur)
    lines = [_title("🤖", "AI", "done" if event in {"complete", "report"} else event), line2]
    if line3_parts:
        lines.append(" · ".join(line3_parts))
    return _finish(lines, payload)


def send_telegram_message(text: str, *, timeout: int = 15, parse_mode: str = "HTML") -> bool:
    creds = _credentials()
    if not creds:
        return False
    token, chat_id = creds
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            ok = bool(payload.get("ok"))
            if not ok:
                logger.warning("telegram send returned non-ok response")
            return ok
    except urllib.error.URLError as exc:
        logger.warning("telegram send failed: %s", exc)
        return False
    except Exception as exc:
        logger.warning("telegram send error: %s", exc)
        return False


def send_telegram_report(payload: dict[str, Any], *, event: str) -> bool:
    if event in QUIET_EVENTS:
        logger.debug("telegram quiet event skipped: %s", event)
        return True
    return send_telegram_message(build_telegram_message(payload, event=event))


def send_ai_enrichment_report(payload: dict[str, Any], *, event: str = "report") -> bool:
    if event in QUIET_EVENTS:
        logger.debug("telegram quiet AI event skipped: %s", event)
        return True
    return send_telegram_message(build_ai_enrichment_message(payload, event=event))
