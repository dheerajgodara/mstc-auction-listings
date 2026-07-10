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


def _fmt_duration(seconds: object) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "n/a"
    if value < 60:
        return f"{value:.1f}s"
    minutes = int(value // 60)
    secs = int(round(value % 60))
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes}m"


def _fmt_source_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return "n/a"
    return ", ".join(f"{source}={count}" for source, count in sorted(counts.items()))


def build_telegram_message(payload: dict[str, Any], *, event: str) -> str:
    status = payload.get("status") or event
    run_id = payload.get("run_id") or "unknown"
    by_source = payload.get("by_source") or {}
    deploy = payload.get("deploy") or {}
    gates = payload.get("safety_gates") or {}
    fallback = payload.get("source_fallback") or {}
    discovery = payload.get("discovery") or {}
    work_plan = payload.get("incremental_work_plan") or {}
    queue = payload.get("incremental_queue") or (work_plan.get("queue") or {})
    batch = payload.get("batch_scrape") or {}
    errors = payload.get("errors") or []
    warnings = payload.get("warnings") or []

    title = {
        "started": "▶️ Scrap Auction India refresh started",
        "comparison_done": "📊 Scrap Auction India comparison complete",
        "deep_scrape_done": "🧰 Scrap Auction India deep scrape complete",
        "success": f"✅ Scrap Auction India refresh {status}",
        "failed": f"❌ Scrap Auction India refresh {status}",
        "blocked": f"🚫 Scrap Auction India refresh {status}",
    }.get(event, f"ℹ️ Scrap Auction India refresh {status}")

    lines = [
        title,
        f"Run: {run_id}",
        f"Started: {payload.get('started_at') or 'n/a'}",
    ]
    if payload.get("finished_at"):
        lines.append(f"Finished: {payload.get('finished_at')}")
    if payload.get("min_closing_date"):
        lines.append(f"Min closing: {payload.get('min_closing_date')}")
    if payload.get("mode"):
        lines.append(f"Mode: {payload.get('mode')} | cap={payload.get('max_deep_scrape_per_run', 'n/a')}")
    if discovery:
        src = discovery.get("by_source") or {}
        if src:
            lines.append(
                f"Discovery: total={discovery.get('count', 'n/a')} "
                f"runtime={_fmt_duration(discovery.get('duration_sec'))} "
                f"({ _fmt_source_counts(src) })"
            )
    if work_plan:
        actions = work_plan.get("selected_action_counts") or work_plan.get("action_counts") or {}
        full_actions = work_plan.get("full_action_counts") or {}
        counts = work_plan.get("full_counts") or work_plan.get("counts") or {}
        if counts:
            lines.append(
                "Compare: "
                + f"new={counts.get('new', 0)} "
                + f"changed={counts.get('changed', 0)} "
                + f"repair={counts.get('needs_repair', 0)} "
                + f"same={counts.get('unchanged', 0)} "
                + f"removed={counts.get('removed', 0)}"
            )
        if actions:
            lines.append(
                "Plan: "
                + f"selected_deep={actions.get('deep_parse', 0)}"
                + f" / full_deep={full_actions.get('deep_parse', actions.get('deep_parse', 0))}"
            )
    if queue:
        lines.append(
            "Queue: "
            + f"selected={queue.get('selected_count', 0)} "
            + f"pending={queue.get('pending_after_selection', 0)} "
            + f"eta_runs={queue.get('estimated_runs_to_clear', 0)}"
        )
    if batch:
        summary = batch.get("manifest_summary") or {}
        if summary:
            lines.append(
                "Deep scrape: "
                + f"done={summary.get('done', 0)} "
                + f"failed={summary.get('failed', 0)} "
                + f"total={summary.get('total', 0)}"
                + f" runtime={_fmt_duration(batch.get('duration_sec'))}"
            )
        if batch.get("docs_budget_remaining") is not None:
            lines.append(f"Docs budget left: {batch.get('docs_budget_remaining')}")
        if batch.get("failed_batches"):
            lines.append("Failed batches: " + ", ".join(str(x) for x in batch.get("failed_batches", [])[:8]))
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
