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


def _clip(text: str, max_chars: int = 500) -> str:
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


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
        "download_started": "⬇️ Scrap Auction India download started",
        "download_selection": "📋 Scrap Auction India download selection",
        "download_done": "✅ Scrap Auction India download complete",
        "download_failed": "❌ Scrap Auction India download failed",
        "download_retry_scheduled": "🔁 Scrap Auction India download retry scheduled",
        "download_retries_exhausted": "🛑 Scrap Auction India download retries exhausted",
        "parse_started": "🧩 Scrap Auction India parse started",
        "parse_selection": "📋 Scrap Auction India parse selection",
        "parse_done": "✅ Scrap Auction India parse complete",
        "parse_failed": "❌ Scrap Auction India parse failed",
        "deploy_started": "🚀 Scrap Auction India deploy started",
        "deploy_done": "✅ Scrap Auction India deploy complete",
        "deploy_failed": "❌ Scrap Auction India deploy failed",
        "drain_started": "🔄 Scrap Auction India drain started",
        "drain_cycle": "🔄 Scrap Auction India drain cycle",
        "drain_done": "✅ Scrap Auction India drain complete",
        "drain_stopped": "🛑 Scrap Auction India drain stopped",
    }.get(event, f"ℹ️ Scrap Auction India {payload.get('pipeline') or 'refresh'} {status}")

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
    if payload.get("pipeline"):
        run_rows.append(_row("Pipeline", payload.get("pipeline")))
    if payload.get("max_download") is not None:
        run_rows.append(_row("Download cap", payload.get("max_download")))
    if payload.get("selected_count") is not None:
        run_rows.append(_row("Selected", payload.get("selected_count")))
    if payload.get("max_cycles") is not None:
        run_rows.append(_row("Max cycles", payload.get("max_cycles")))
    if payload.get("cycles_completed") is not None:
        run_rows.append(_row("Cycles done", payload.get("cycles_completed")))
    if payload.get("cycle") is not None:
        run_rows.append(_row("Cycle", payload.get("cycle")))
    if payload.get("retry_attempt") is not None:
        run_rows.append(_row("Retry attempt", payload.get("retry_attempt")))
    if payload.get("wait_minutes") is not None:
        run_rows.append(_row("Retry wait (min)", payload.get("wait_minutes")))
    if payload.get("parse_backlog_start") is not None:
        run_rows.append(_row("Parse backlog start", payload.get("parse_backlog_start")))
    if payload.get("parse_backlog_end") is not None:
        run_rows.append(_row("Parse backlog end", payload.get("parse_backlog_end")))
    if payload.get("remaining_after") is not None:
        run_rows.append(_row("Remaining after cycle", payload.get("remaining_after")))
    lines.extend(_section("Run", run_rows))

    ledger = payload.get("ledger") or {}
    if ledger:
        ledger_rows = [
            _row("Total", ledger.get("total", "n/a")),
            _row("Download", ledger.get("download") or "n/a"),
            _row("Parse", ledger.get("parse") or "n/a"),
            _row("Deploy ready", ledger.get("deploy_ready", "n/a")),
        ]
        if payload.get("estimated_runs_to_clear") is not None:
            ledger_rows.append(_row("Est. download runs", payload.get("estimated_runs_to_clear")))
        if payload.get("download_ok") is not None:
            ledger_rows.append(_row("Download ok/fail", f"{payload.get('download_ok')}/{payload.get('download_failed')}"))
        if payload.get("parse_ok") is not None:
            ledger_rows.append(_row("Parse ok/fail", f"{payload.get('parse_ok')}/{payload.get('parse_failed')}"))
        lines.extend(_section("Ledger", ledger_rows))

    if discovery:
        src = discovery.get("by_source") or {}
        discovery_rows = []
        discovery_rows.append(_row("Total", discovery.get("count", "n/a")))
        discovery_rows.append(_row("Runtime", _fmt_duration(discovery.get("duration_sec"))))
        if src:
            discovery_rows.append(_row("Sources", _fmt_source_counts(src)))
        discovery_fallback = discovery.get("source_fallback") or {}
        if discovery_fallback.get("applied"):
            discovery_rows.append(
                _row(
                    "Source fallback",
                    ", ".join(str(s) for s in (discovery_fallback.get("sources") or {}).keys()) or "yes",
                )
            )
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
        error_rows = [_row("Details", _short_join(errors, limit=4, max_chars=900))]
        build = payload.get("build") or {}
        if build.get("failed_step"):
            error_rows.append(_row("Failed step", build.get("failed_step")))
        if build.get("stderr_tail"):
            error_rows.append(_row("Build stderr", _clip(str(build.get("stderr_tail")), 500)))
        lines.extend(_section("Errors", error_rows))
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


def build_ai_enrichment_message(payload: dict[str, Any], *, event: str = "report") -> str:
    selection = payload.get("selection") or {}
    cache = payload.get("cache_stats") or {}
    budget = payload.get("budget") or {}
    details = payload.get("details") or []
    ready_models: dict[str, int] = {}
    for detail in details:
        model = detail.get("model")
        if model:
            ready_models[str(model)] = ready_models.get(str(model), 0) + 1

    title = {
        "started": "▶️ Scrap Auction India AI enrichment started",
        "selection_done": "📊 Scrap Auction India AI selection complete",
        "complete": "🤖 Scrap Auction India AI enrichment complete",
        "failed": "❌ Scrap Auction India AI enrichment failed",
        "skipped": "⏭️ Scrap Auction India AI enrichment skipped",
        "report": "🤖 Scrap Auction India AI enrichment report",
    }.get(event, "🤖 Scrap Auction India AI enrichment report")
    lines = [f"<b>{_h(title)}</b>"]
    lines.extend(
        _section(
            "Run",
            [
                _row("Run", payload.get("run_id", "n/a")),
                _row("Started", payload.get("started_at", "n/a")),
                *([_row("Finished", payload.get("finished_at"))] if payload.get("finished_at") else []),
                *([_row("Slot", payload.get("slot_ist"))] if payload.get("slot_ist") else []),
                _row("Mode", "live OpenRouter" if payload.get("allow_network") else "mock/no-network"),
                _row("Processed", payload.get("processed", 0)),
                _row("Ready", payload.get("ready", 0)),
                _row("Skipped", payload.get("skipped", 0)),
                _row("Rejected", payload.get("rejected", 0)),
                _row("Failed", payload.get("failed", 0)),
                _row("Prompt/schema", f"{payload.get('prompt_version')} / {payload.get('schema_version')}"),
                *([_row("Runtime", _fmt_duration(payload.get("duration_sec")))] if payload.get("duration_sec") is not None else []),
            ],
        )
    )
    lines.extend(
        _section(
            "Priority Selection",
            [
                _row("Eligible", selection.get("eligible", "n/a")),
                _row("Selected", selection.get("selected", "n/a")),
                _row("Already enriched", selection.get("already_ai_done", "n/a")),
                _row("Current cache skipped", selection.get("current_cache_skipped", "n/a")),
                _row("Remaining after selection", selection.get("remaining_after_selection", "n/a")),
                _row("Estimated runs left", selection.get("estimated_runs_to_clear", "n/a")),
                _row("Sources", _fmt_source_counts(selection.get("selected_by_source") or {})),
            ],
        )
    )
    if budget:
        lines.extend(
            _section(
                "Daily Budget",
                [
                    _row("Date", budget.get("date", "n/a")),
                    _row("Budget", budget.get("daily_budget", "n/a")),
                    _row("Attempted today", budget.get("attempted_today", "n/a")),
                    _row("Remaining today", budget.get("remaining_today", "n/a")),
                ],
            )
        )
    ledger_sync = payload.get("ledger_sync") or []
    if ledger_sync:
        rows = []
        for event in ledger_sync:
            status = "OK" if event.get("ok") else "FAILED"
            action = event.get("action", "sync")
            message = event.get("message") or ""
            rows.append(_row(str(action).title(), f"{status} | {message}"))
        lines.extend(_section("Durable Ledger", rows))
    if payload.get("error"):
        lines.extend(_section("Error", [_row("Reason", payload.get("error"))]))
    reasons = selection.get("priority_reason_counts") or {}
    if reasons:
        top_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:8]
        lines.extend(
            _section(
                "Why These Listings",
                [_row("Top reasons", ", ".join(f"{k}={v}" for k, v in top_reasons))],
            )
        )
    top_selected = selection.get("top_selected") or []
    if top_selected:
        rows = []
        for item in top_selected[:5]:
            rows.append(
                _row(
                    str(item.get("auction_id")),
                    f"score={item.get('score')} | {', '.join((item.get('reasons') or [])[:3])}",
                )
            )
        lines.extend(_section("Top Selected", rows))
    failure_reasons: dict[str, int] = {}
    for detail in details:
        if detail.get("status") == "failed":
            reason = str(detail.get("reason") or "unknown")
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    if failure_reasons:
        lines.extend(_section("Failure Reasons", [_row("Reasons", _fmt_source_counts(failure_reasons))]))
    cache_rows = [
        _row("Ready cache", cache.get("ready", 0)),
        _row("Rejected cache", cache.get("rejected", 0)),
        _row("Failed cache", cache.get("failed", 0)),
        _row("Total cache", cache.get("total", 0)),
    ]
    lines.extend(_section("Cache", cache_rows))
    if ready_models:
        lines.extend(_section("Models", [_row("Used", _fmt_source_counts(ready_models))]))
    links = []
    if payload.get("github_run_url"):
        links.append(_link("GitHub", payload.get("github_run_url")))
    if links:
        lines.extend(_section("Links", links))
    return "\n".join(lines)


def send_ai_enrichment_report(payload: dict[str, Any], *, event: str = "report") -> bool:
    return send_telegram_message(build_ai_enrichment_message(payload, event=event))
