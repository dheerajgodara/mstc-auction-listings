"""World-class Telegram ops cards for Scrap Auction India.

Severity: silent | progress | digest | action | critical
Typography: HTML only — title → outcome → metrics · metrics → context → link
Lane card only — no legacy emoji event spam.
"""

from __future__ import annotations

import json
import logging
import os
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from typing import Any, Literal

logger = logging.getLogger("scraper.telegram_reporter")

Severity = Literal["silent", "progress", "digest", "action", "critical"]

LANE_LABELS: dict[str, str] = {
    "discover_mstc": "Discover MSTC",
    "discover_gem": "Discover GeM",
    "download_mstc": "Download MSTC",
    "download_gem": "Download GeM",
    "publish_media": "Upload media",
    "parse": "Process catalogues",
    "build_deploy": "Update site",
    "pipeline": "Catalogue pipeline",
}

LANE_BANNED_PHRASES: frozenset[str] = frozenset(
    {
        "fail budget",
        "timebox",
        "pdfs_on_disk",
        "parsed_on_disk",
        "parse_eligible",
        "publishable",
        "backlog left",
        "auto-resume",
        "snapshot",
        "schema",
        "workers",
        "wave",
        "hostinger",
        "ready merged",
        "material-searchable",
        "ledger",
        "batch",
        "rsync",
        "flush",
        "eligible",
        "fetched_local",
        "pipeline_",
        "quarantine",
    }
)

PROGRESS_MAX_CHARS = 320
ACTION_MAX_CHARS = 480
DIGEST_MAX_CHARS = 700
LANE_MAX_CHARS = PROGRESS_MAX_CHARS
MAX_MESSAGE_CHARS = ACTION_MAX_CHARS

_last_send_mono = 0.0
_recent_fingerprints: dict[str, float] = {}


def _credentials() -> tuple[str, str] | None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return None
    return token, chat_id


def _h(value: object) -> str:
    return escape(str(value), quote=False)


def _fmt_int(n: int) -> str:
    return f"{n:,}"


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


def _fmt_rate(ok: int, wall_seconds: object) -> str:
    try:
        wall = float(wall_seconds)
    except (TypeError, ValueError):
        return ""
    if wall < 30 or ok < 3:
        return ""
    rate = ok / (wall / 60.0)
    if rate >= 10:
        return f"{rate:.0f}/min"
    return f"{rate:.1f}/min"


def _clip(text: str, max_chars: int = 120) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    cut = value[: max_chars - 1].rsplit(" ", 1)[0]
    return (cut or value[: max_chars - 1]).rstrip() + "…"


def _ist_now_short() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b · %H:%M IST")


def _github_run_url_from_env() -> str:
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def _i(stats: dict[str, Any], *keys: str, default: int = 0) -> int:
    for k in keys:
        if stats.get(k) is not None:
            try:
                return int(stats[k])
            except (TypeError, ValueError):
                continue
    return default


def _in_quiet_hours() -> bool:
    raw = (os.environ.get("TELEGRAM_QUIET_HOURS_IST") or "").strip()
    if not raw or "-" not in raw:
        return False
    try:
        start_s, end_s = raw.split("-", 1)
        start, end = int(start_s), int(end_s)
    except ValueError:
        return False
    from datetime import datetime
    from zoneinfo import ZoneInfo

    hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit("\n", 1)[0]
    return (cut or text[: max_chars - 1]).rstrip() + "…"


def _open_run_link(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    return f'<a href="{escape(url, quote=True)}">Open run</a>'


def _join_metrics(parts: list[str]) -> str:
    return " · ".join(p for p in parts if p)


def build_lane_card(
    lane: str,
    severity: Severity,
    stats: dict[str, Any] | None = None,
    *,
    error: str | None = None,
    run_url: str | None = None,
) -> str:
    if severity == "silent":
        return ""
    stats = dict(stats or {})
    label = LANE_LABELS.get(lane, lane.replace("_", " ").title())
    url = (run_url or stats.get("github_run_url") or _github_run_url_from_env() or "").strip()
    err = _clip(error or str(stats.get("error") or ""), 120)

    if severity in {"action", "critical"} or str(stats.get("event") or "") == "failed":
        return _build_failure_or_action(label, severity, err, url, stats)

    if severity == "digest" or lane == "digest":
        return build_daily_digest_message(stats)

    return _build_progress(lane, label, stats, url)


def _download_result_line(stats: dict[str, Any]) -> str:
    """Compact OK/fail/rate line for download lanes (progress and attention cards)."""
    ok = _i(stats, "downloaded", "ok_count")
    failed = _i(stats, "failed", "fail_count")
    if ok == 0 and failed == 0:
        return ""
    attempted = ok + failed
    parts = [f"{_fmt_int(ok)} OK"]
    if failed:
        parts.append(f"{_fmt_int(failed)} failed")
    if attempted > 0:
        pct = round(100.0 * ok / attempted)
        parts.append(f"{pct}% ok")
    rate = _fmt_rate(ok, stats.get("wall_seconds"))
    if rate:
        parts.append(rate)
    return _join_metrics(parts)


def _download_backlog_line(stats: dict[str, Any]) -> str:
    need = _i(stats, "still_need_files", "download_pending", "backlog_left")
    ready_proc = _i(stats, "ready_to_process")
    live = _i(stats, "live_on_site", "live_export_count")
    ctx_parts = []
    if need:
        ctx_parts.append(f"Still need files: {_fmt_int(need)}")
    if ready_proc:
        ctx_parts.append(f"Ready to process: {_fmt_int(ready_proc)}")
    if live:
        ctx_parts.append(f"Live on site: {_fmt_int(live)}")
    return _join_metrics(ctx_parts) if ctx_parts else ""


def _build_failure_or_action(
    label: str,
    severity: Severity,
    err: str,
    url: str,
    stats: dict[str, Any],
) -> str:
    lines = [f"<b>{_h(label)}</b>", ""]
    # Prefer real wave numbers over a bare pass/fail headline.
    numbers = _download_result_line(stats)
    if numbers:
        lines.append(numbers)
        backlog = _download_backlog_line(stats)
        if backlog:
            lines.append(backlog)
    if severity == "critical" or str(stats.get("event") or "") == "failed":
        outcome = str(stats.get("outcome") or "").strip()
        if outcome:
            lines.append(f"<b>FAILED</b> — {_h(_clip(outcome, 80))}")
        else:
            lines.append("<b>FAILED</b>")
    else:
        outcome = str(stats.get("outcome") or "Needs attention").strip()
        if numbers:
            # Numbers already carry the story; keep attention as a short flag.
            if outcome == "Needs attention":
                lines.append("<b>Needs attention</b> — high fail share this wave")
            else:
                lines.append(f"<b>Needs attention</b> — {_h(_clip(outcome, 100))}")
        else:
            lines.append(f"<b>Needs attention</b> — {_h(_clip(outcome, 100))}")
    if err:
        lines.append(f"<code>{_h(err)}</code>")
    context = str(stats.get("context") or "").strip()
    if context:
        lines.append(_h(_clip(context, 160)))
    link = _open_run_link(url)
    if link:
        lines.append(link)
    return _trim("\n".join(lines), ACTION_MAX_CHARS)


def _build_progress(lane: str, label: str, stats: dict[str, Any], url: str) -> str:
    lines: list[str] = [f"<b>{_h(label)}</b>"]

    if lane.startswith("discover_"):
        listed = _i(stats, "listed")
        new = _i(stats, "new")
        queued = _i(stats, "queued_download", "queued")
        if listed == 0 and new == 0 and queued == 0:
            lines.append("Nothing new to queue")
        else:
            lines.append(
                _join_metrics(
                    [
                        f"Found {_fmt_int(listed)} live",
                        f"{_fmt_int(new)} new",
                        f"{_fmt_int(queued)} queued",
                    ]
                )
            )
        ctx_parts = []
        need = _i(stats, "still_need_files", "download_pending")
        ready_proc = _i(stats, "ready_to_process")
        live = _i(stats, "live_on_site", "live_export_count")
        if need:
            ctx_parts.append(f"Still need files: {_fmt_int(need)}")
        if ready_proc:
            ctx_parts.append(f"Ready to process: {_fmt_int(ready_proc)}")
        if live:
            ctx_parts.append(f"Live on site: {_fmt_int(live)}")
        if ctx_parts:
            lines.append(_join_metrics(ctx_parts))

    elif lane.startswith("download_"):
        added = _i(stats, "downloaded", "ok_count")
        failed = _i(stats, "failed", "fail_count")
        if added == 0 and failed == 0:
            lines.append("No new files this run")
        else:
            lines.append(_download_result_line(stats))
        backlog = _download_backlog_line(stats)
        if backlog:
            lines.append(backlog)

    elif lane == "publish_media":
        added = _i(stats, "ok_count", "downloaded")
        failed = _i(stats, "fail_count", "failed")
        if added == 0 and failed == 0:
            return ""
        parts = [f"+{_fmt_int(added)} uploaded"]
        if failed:
            parts.append(f"{_fmt_int(failed)} failed")
        lines.append(_join_metrics(parts))
        rem = _i(stats, "remaining", "ready_for_site")
        if rem:
            lines.append(f"Still waiting to upload: {_fmt_int(rem)}")

    elif lane == "parse":
        parsed = _i(stats, "parsed")
        failed = _i(stats, "failed")
        skipped = _i(stats, "skipped_fresh", "skipped")
        rate = _fmt_rate(parsed, stats.get("wall_seconds"))
        if parsed == 0 and failed == 0:
            lines.append("Nothing new to process this run")
        else:
            parts = [f"+{_fmt_int(parsed)} processed"]
            if skipped:
                parts.append(f"{_fmt_int(skipped)} already done")
            if failed:
                parts.append(f"{_fmt_int(failed)} failed")
            if rate:
                parts.append(rate)
            lines.append(_join_metrics(parts))
        ctx_parts = []
        ready_proc = _i(stats, "ready_to_process", "backlog_left")
        ready_site = _i(stats, "ready_for_site", "publishable_future")
        live = _i(stats, "live_on_site", "live_export_count")
        if ready_proc:
            ctx_parts.append(f"Ready to process: {_fmt_int(ready_proc)}")
        if ready_site:
            ctx_parts.append(f"Ready for site: {_fmt_int(ready_site)}")
        if live:
            ctx_parts.append(f"Live: {_fmt_int(live)}")
        if ctx_parts:
            lines.append(_join_metrics(ctx_parts))

    elif lane == "build_deploy":
        live = _i(stats, "published", "live_on_site", "live_export_count", "export_count")
        aged = _i(stats, "aged_out", "aged_out_parsed", "aged_out_stripped")
        ready_site = _i(stats, "ready_for_site", "publishable_future")
        if live == 0 and stats.get("allow_small_export"):
            lines.append("Cutover: allowed empty export")
        else:
            lines.append(f"Live on site: {_fmt_int(live)}")
        extra = []
        if ready_site and ready_site != live:
            extra.append(f"Ready for site: {_fmt_int(ready_site)}")
        if aged:
            extra.append(f"~{_fmt_int(aged)} finished but closing already passed — expected")
        if extra:
            lines.append(_join_metrics(extra))

    else:
        status = str(stats.get("status") or stats.get("outcome") or "Done")
        lines.append(_h(status))

    if stats.get("include_run_link") and url:
        link = _open_run_link(url)
        if link:
            lines.append(link)

    return _trim("\n".join(lines), PROGRESS_MAX_CHARS)


def build_daily_digest_message(snapshot: dict[str, Any]) -> str:
    lines = [
        "<b>Daily catalogue</b>",
        _h(str(snapshot.get("when") or _ist_now_short())),
    ]
    live = _i(snapshot, "live_on_site", "live")
    ready = _i(snapshot, "ready_for_site", "ready")
    need = _i(snapshot, "still_need_files", "need_files")
    lines.append(
        _join_metrics(
            [
                f"Live on site: {_fmt_int(live)}",
                f"Ready for site: {_fmt_int(ready)}",
                f"Still need files: {_fmt_int(need)}",
            ]
        )
    )
    dl = _i(snapshot, "downloaded_yesterday", "downloaded")
    parsed = _i(snapshot, "processed_yesterday", "processed", "parsed")
    failed = _i(snapshot, "failed_yesterday", "failed")
    yparts = []
    if dl or parsed or failed:
        if dl:
            yparts.append(f"+{_fmt_int(dl)} downloaded")
        if parsed:
            yparts.append(f"+{_fmt_int(parsed)} processed")
        if failed:
            yparts.append(f"{_fmt_int(failed)} failed")
        lines.append("Yesterday: " + _join_metrics(yparts))
    if snapshot.get("all_clear", True) and failed == 0:
        lines.append("All clear")
    elif snapshot.get("note"):
        lines.append(_h(_clip(str(snapshot["note"]), 120)))
    lines.append("<i>Only listings closing after 12h are queued.</i>")
    return _trim("\n".join(lines), DIGEST_MAX_CHARS)


def build_ops_note_message(title: str, body: str, *, bullets: list[str] | None = None) -> str:
    lines = [f"<b>{_h(title)}</b>"]
    if body:
        lines.append(_h(_clip(body, 200)))
    for item in (bullets or [])[:5]:
        lines.append(f"· {_h(_clip(item, 120))}")
    return _trim("\n".join(lines), ACTION_MAX_CHARS)


def _fingerprint(lane: str, severity: Severity, stats: dict[str, Any]) -> str:
    bucket = _i(stats, "still_need_files", "backlog_left", "ready_for_site", "downloaded", "parsed")
    bucket = (bucket // 50) * 50
    return f"{lane}|{severity}|{bucket}|{_i(stats, 'failed')}"


def _dedupe_ok(fp: str, *, ttl_sec: float = 600.0) -> bool:
    now = time.monotonic()
    stale = [k for k, t in _recent_fingerprints.items() if now - t > ttl_sec]
    for k in stale:
        _recent_fingerprints.pop(k, None)
    if fp in _recent_fingerprints:
        return False
    _recent_fingerprints[fp] = now
    return True


def _pace_send(severity: Severity) -> None:
    global _last_send_mono
    delay = 0.05 if severity in {"critical", "action"} else 0.3
    now = time.monotonic()
    wait = delay - (now - _last_send_mono)
    if wait > 0:
        time.sleep(wait)
    _last_send_mono = time.monotonic()


def send_html_card(text: str, *, timeout: int = 15) -> bool:
    text = (text or "").strip()
    if not text:
        return True
    creds = _credentials()
    if not creds:
        return False
    token, chat_id = creds
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(3):
        data = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(api, data=data, method="POST")
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                ok = bool(payload.get("ok"))
                if not ok:
                    logger.warning("telegram send returned non-ok response")
                return ok
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                retry_after = 2.0
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    retry_after = float((body.get("parameters") or {}).get("retry_after") or 2)
                except Exception:
                    pass
                time.sleep(retry_after + random.uniform(0, 0.5))
                continue
            logger.warning("telegram send failed: %s", exc)
            return False
        except urllib.error.URLError as exc:
            logger.warning("telegram send failed: %s", exc)
            return False
        except Exception as exc:
            logger.warning("telegram send error: %s", exc)
            return False
    return False


def send_telegram_message(text: str, *, timeout: int = 15, parse_mode: str = "HTML") -> bool:
    _ = parse_mode
    return send_html_card(text, timeout=timeout)


def classify_lane_severity(
    lane: str,
    event: str,
    stats: dict[str, Any],
    *,
    noop: bool = False,
) -> Severity:
    if noop:
        return "silent"
    if event == "failed":
        return "critical" if lane == "build_deploy" else "action"
    if lane == "publish_media":
        if _i(stats, "ok_count", "downloaded") == 0 and _i(stats, "fail_count", "failed") == 0:
            return "silent"
    if lane.startswith("discover_"):
        if _i(stats, "new") == 0 and _i(stats, "queued_download", "queued") == 0:
            return "silent"
    if lane.startswith("download_"):
        if _i(stats, "downloaded", "ok_count") == 0 and _i(stats, "failed") == 0:
            return "silent"
        # MSTC portal 500s routinely produce 10–25 fails in a healthy 150-cap wave.
        # Prefer progress cards with real OK/fail counts; only escalate when the wave
        # actually looks broken (majority fail, zero OK, or health abort).
        ok = _i(stats, "downloaded", "ok_count")
        fail = _i(stats, "failed", "fail_count")
        attempted = ok + fail
        status = str(stats.get("status") or "").strip().lower()
        if status in {"aborted_health", "aborted"}:
            return "action"
        if attempted >= 4 and ok == 0:
            return "action"
        if attempted >= 4 and (fail / attempted) >= 0.5:
            return "action"
        return "progress"
    if lane == "parse":
        if (
            _i(stats, "parsed") == 0
            and _i(stats, "failed") == 0
            and _i(stats, "skipped_fresh", "skipped") == 0
        ):
            return "silent"
    ok = _i(stats, "downloaded", "parsed", "ok_count")
    fail = _i(stats, "failed", "fail_count")
    attempted = ok + fail
    if attempted >= 4 and fail >= 10:
        return "action"
    if attempted >= 4 and (fail / attempted) >= 0.25:
        return "action"
    return "progress"


def send_lane_card(
    lane: str,
    severity: Severity | None = None,
    stats: dict[str, Any] | None = None,
    *,
    event: str = "finished",
    noop: bool = False,
    run_url: str | None = None,
    error: str | None = None,
) -> bool:
    from scraper.config import TELEGRAM_NOOP_SILENT

    stats = dict(stats or {})
    if not stats.get("github_run_url"):
        stats["github_run_url"] = run_url or _github_run_url_from_env()

    sev = severity or classify_lane_severity(lane, event, stats, noop=noop)
    if sev == "silent" or (noop and TELEGRAM_NOOP_SILENT):
        logger.debug("telegram silent: lane=%s", lane)
        return True
    if sev == "progress" and _in_quiet_hours():
        logger.debug("telegram quiet hours skip progress: lane=%s", lane)
        return True
    if event == "failed":
        stats["event"] = "failed"
        if lane == "build_deploy":
            sev = "critical"
        elif sev == "progress":
            sev = "action"

    fp = _fingerprint(lane, sev, stats)
    if sev == "progress" and not _dedupe_ok(fp):
        logger.debug("telegram dedupe skip: %s", fp)
        return True

    text = build_lane_card(
        lane, sev, stats, error=error or stats.get("error"), run_url=stats.get("github_run_url")
    )
    if not text:
        return True
    _pace_send(sev)
    return send_html_card(text)


def send_lane_report(
    lane: str,
    event: str,
    stats: dict[str, Any] | None = None,
    *,
    noop: bool = False,
) -> bool:
    return send_lane_card(lane, event=event, stats=stats, noop=noop)


def send_daily_digest(snapshot: dict[str, Any] | None = None) -> bool:
    text = build_daily_digest_message(dict(snapshot or {}))
    _pace_send("digest")
    return send_html_card(text)


def send_ops_note(title: str, body: str = "", *, bullets: list[str] | None = None) -> bool:
    return send_html_card(build_ops_note_message(title, body, bullets=bullets))


def send_action_card(
    lane: str,
    outcome: str,
    *,
    context: str = "",
    error: str = "",
    run_url: str | None = None,
    critical: bool = False,
) -> bool:
    stats = {
        "outcome": outcome,
        "context": context,
        "error": error,
        "github_run_url": run_url or _github_run_url_from_env(),
        "include_run_link": True,
    }
    return send_lane_card(
        lane,
        "critical" if critical else "action",
        stats,
        error=error or None,
    )


def build_lane_message(lane: str, event: str, stats: dict[str, Any]) -> str:
    sev = classify_lane_severity(lane, event, stats)
    if event == "failed":
        sev = "critical" if lane == "build_deploy" else "action"
    return build_lane_card(lane, sev, stats, error=stats.get("error"))


def build_telegram_message(payload: dict[str, Any], *, event: str) -> str:
    _ = payload, event
    return ""


def send_telegram_report(payload: dict[str, Any], *, event: str) -> bool:
    logger.debug("telegram legacy event suppressed: %s", event)
    _ = payload
    return True


def send_ai_enrichment_report(payload: dict[str, Any], *, event: str = "report") -> bool:
    logger.info("AI telegram suppressed (enricher held): event=%s", event)
    _ = payload
    return True


def build_ai_enrichment_message(payload: dict[str, Any], *, event: str = "report") -> str:
    _ = payload, event
    return ""
