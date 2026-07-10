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


def _h(value: object) -> str:
    return escape(str(value), quote=False)


def _section(title: str, rows: list[str]) -> list[str]:
    if not rows:
        return []
    return [f"\n<b>{_h(title)}</b>", *rows]


def _row(label: str, value: object) -> str:
    return f"• <b>{_h(label)}:</b> {_h(value)}"


def _link(label: str, url: object) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    safe_url = escape(text, quote=True)
    return f"• <b>{_h(label)}:</b> <a href=\"{safe_url}\">{_h(text)}</a>"


def _short_join(values: list[Any], *, limit: int = 4, max_chars: int = 700) -> str:
    text = "; ".join(str(v) for v in values[:limit])
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


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
        f"<b>{_h(title)}</b>",
    ]

    run_rows = [
        _row("Run", run_id),
        _row("Started", payload.get("started_at") or "n/a"),
    ]
    if payload.get("finished_at"):
        run_rows.append(_row("Finished", payload.get("finished_at")))
    if payload.get("min_closing_date"):
        run_rows.append(_row("Min closing", payload.get("min_closing_date")))
    if payload.get("mode"):
        run_rows.append(_row("Mode", f"{payload.get('mode')} | cap={payload.get('max_deep_scrape_per_run', 'n/a')}"))
    lines.extend(_section("Run", run_rows))

    if discovery:
        src = discovery.get("by_source") or {}
        discovery_rows = []
        discovery_rows.append(_row("Total", discovery.get("count", "n/a")))
        discovery_rows.append(_row("Runtime", _fmt_duration(discovery.get("duration_sec"))))
        if src:
            discovery_rows.append(_row("Sources", _fmt_source_counts(src)))
        lines.extend(_section("Discovery", discovery_rows))

    if work_plan:
        actions = work_plan.get("selected_action_counts") or work_plan.get("action_counts") or {}
        full_actions = work_plan.get("full_action_counts") or {}
        counts = work_plan.get("full_counts") or work_plan.get("counts") or {}
        compare_rows = []
        if counts:
            compare_rows.append(
                _row(
                    "Changes",
                    f"new={counts.get('new', 0)}, changed={counts.get('changed', 0)}, "
                    f"repair={counts.get('needs_repair', 0)}, same={counts.get('unchanged', 0)}, "
                    f"removed={counts.get('removed', 0)}",
                )
            )
        if actions:
            compare_rows.append(
                _row(
                    "Deep scrape plan",
                    f"selected={actions.get('deep_parse', 0)} / candidates={full_actions.get('deep_parse', actions.get('deep_parse', 0))}",
                )
            )
        lines.extend(_section("Comparison", compare_rows))

    if queue:
        queue_rows = [
            _row("Selected this run", queue.get("selected_count", 0)),
            _row("Pending after selection", queue.get("pending_after_selection", 0)),
            _row("Estimated runs to clear", queue.get("estimated_runs_to_clear", 0)),
        ]
        lines.extend(_section("Queue", queue_rows))

    if batch:
        summary = batch.get("manifest_summary") or {}
        batch_rows = []
        selected = (queue or {}).get("selected_count")
        if selected is not None:
            batch_rows.append(_row("Selected auctions", selected))
        if summary:
            batch_rows.append(
                _row(
                    "Batches",
                    f"{summary.get('done', 0)} done / {summary.get('failed', 0)} failed / {summary.get('total', 0)} total",
                )
            )
            batch_rows.append(_row("Runtime", _fmt_duration(batch.get("duration_sec"))))
        if batch.get("docs_budget_remaining") is not None:
            batch_rows.append(_row("Docs budget left", batch.get("docs_budget_remaining")))
        if batch.get("failed_batches"):
            batch_rows.append(_row("Failed batches", ", ".join(str(x) for x in batch.get("failed_batches", [])[:8])))
        lines.extend(_section("Deep Scrape", batch_rows))

    result_rows = []
    if payload.get("total_auctions") is not None:
        result_rows.append(_row("Auctions", payload.get("total_auctions")))
        result_rows.append(_row("Lots", payload.get("total_lots")))
    if by_source:
        result_rows.append(_row("Sources", _fmt_source_counts(by_source)))
    if gates:
        result_rows.append(_row("Safety gates", _fmt_bool(gates.get("passed"))))
    if fallback.get("applied"):
        parts = [
            f"{source}+{info.get('carried_forward', 0)} carried"
            for source, info in (fallback.get("sources") or {}).items()
        ]
        result_rows.append(_row("Fallback", ", ".join(parts)))
    if deploy:
        result_rows.append(_row("Deploy", _fmt_bool(deploy.get("deployed"))))
    lines.extend(_section("Result", result_rows))

    link_rows = []
    if payload.get("github_run_url"):
        link_rows.append(_link("GitHub", payload["github_run_url"]))
    if payload.get("site_base_url"):
        link_rows.append(_link("Site", payload["site_base_url"]))
    lines.extend(_section("Links", link_rows))

    if errors:
        lines.extend(
            _section(
                "Errors",
                [_row("Details", _short_join(errors, limit=4, max_chars=900))],
            )
        )
    elif warnings:
        lines.extend(
            _section(
                "Warnings",
                [_row("Details", _short_join(warnings, limit=3, max_chars=700))],
            )
        )
    return "\n".join(lines)


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
    return send_telegram_message(build_telegram_message(payload, event=event))
