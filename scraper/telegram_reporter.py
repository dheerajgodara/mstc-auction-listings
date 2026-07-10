from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("scraper.telegram_reporter")


def _credentials() -> tuple[str, str] | None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return None
    return token, chat_id


def _fmt_bool(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def build_telegram_message(payload: dict[str, Any], *, event: str) -> str:
    status = payload.get("status") or event
    run_id = payload.get("run_id") or "unknown"
    by_source = payload.get("by_source") or {}
    deploy = payload.get("deploy") or {}
    gates = payload.get("safety_gates") or {}
    fallback = payload.get("source_fallback") or {}
    errors = payload.get("errors") or []
    warnings = payload.get("warnings") or []

    icon = {
        "started": "▶️",
        "success": "✅",
        "failed": "❌",
        "blocked": "🚫",
    }.get(event, "ℹ️")
    title = f"{icon} Scrap Auction India refresh {status}"

    lines = [
        title,
        f"Run: {run_id}",
        f"Started: {payload.get('started_at') or 'n/a'}",
    ]
    if payload.get("finished_at"):
        lines.append(f"Finished: {payload.get('finished_at')}")
    if payload.get("min_closing_date"):
        lines.append(f"Min closing: {payload.get('min_closing_date')}")
    if payload.get("total_auctions") is not None:
        lines.append(f"Auctions: {payload.get('total_auctions')} | Lots: {payload.get('total_lots')}")
    if by_source:
        lines.append(
            "Sources: "
            + ", ".join(f"{source}={count}" for source, count in sorted(by_source.items()))
        )
    if gates:
        lines.append(f"Safety gates: {_fmt_bool(gates.get('passed'))}")
    if fallback.get("applied"):
        parts = []
        for source, info in (fallback.get("sources") or {}).items():
            parts.append(f"{source}+{info.get('carried_forward', 0)} carried")
        lines.append("Fallback: " + ", ".join(parts))
    if deploy:
        lines.append(f"Deploy: {_fmt_bool(deploy.get('deployed'))}")
    if payload.get("github_run_url"):
        lines.append(f"GitHub: {payload['github_run_url']}")
    if payload.get("site_base_url"):
        lines.append(f"Site: {payload['site_base_url']}")
    if errors:
        lines.append("Errors: " + "; ".join(str(e) for e in errors[:4]))
    elif warnings:
        lines.append("Warnings: " + "; ".join(str(w) for w in warnings[:3]))
    return "\n".join(lines)


def send_telegram_message(text: str, *, timeout: int = 15) -> bool:
    creds = _credentials()
    if not creds:
        return False
    token, chat_id = creds
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
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
    return send_telegram_message(build_telegram_message(payload, event=event))
