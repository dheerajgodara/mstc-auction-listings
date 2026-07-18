"""Plain-language Telegram status for Scrap Auction India pipelines.

Design rules (readable on a phone without decoding jargon):
- Title: emoji + what happened
- Body: short sentences a non-engineer can follow
- Queue line: downloaded / waiting to process / ready for site
- Optional GitHub log link
- Soft limit ~550 chars; no run_id / timestamp dumps
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
        "discover_started",
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

MAX_MESSAGE_CHARS = 550


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
    return f'<a href="{escape(url, quote=True)}">full log</a>'


def _queue_line(ledger: dict[str, Any] | None) -> str:
    """Human queue snapshot: downloaded / waiting / ready for site."""
    if not ledger:
        return ""
    parts: list[str] = []
    dl = ledger.get("download")
    if isinstance(dl, dict) and dl:
        done = int(dl.get("done") or 0)
        pending = int(dl.get("pending") or 0)
        failed = int(dl.get("failed") or 0)
        bit = f"downloaded {done}"
        if pending:
            bit += f" · still need files {pending}"
        if failed:
            bit += f" · download failed {failed}"
        parts.append(bit)
    awaiting = ledger.get("awaiting_hostinger_sync")
    if awaiting:
        parts.append(f"waiting on server sync {int(awaiting)}")
    parse = ledger.get("parse")
    if isinstance(parse, dict) and parse:
        done = int(parse.get("done") or 0)
        waiting = int(parse.get("pending") or 0) + int(parse.get("failed") or 0)
        if waiting:
            parts.append(f"waiting to process {waiting}")
        else:
            parts.append(f"processed {done} · nothing waiting")
    ready = ledger.get("deploy_ready")
    if ready not in (None, ""):
        parts.append(f"ready for site {ready}")
    if not parts:
        return ""
    return "Queue: " + " · ".join(parts)


def _finish(lines: list[str], payload: dict[str, Any]) -> str:
    link = _run_link(payload)
    if link:
        lines.append(link)
    text = "\n".join(line for line in lines if line is not None and str(line).strip() != "")
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"
    return text


def _title(emoji: str, headline: str) -> str:
    return f"<b>{_h(emoji)} {_h(headline)}</b>"


def _prefer_fail_summary(raw: str) -> str:
    """Keep FAIL check labels when present; otherwise return cleaned error text."""
    from scraper.verify_fail_extract import extract_fail_lines

    text = str(raw or "").strip()
    if not text:
        return ""
    # Already a short summary from pipeline_deploy._run
    if "FAIL " in text and "\n" not in text:
        return text
    fails = extract_fail_lines(text, limit=3)
    if fails:
        return "; ".join(f"FAIL {label}" for label in fails)
    # Drop huge OK tails: keep first line of RuntimeError-style messages
    first = text.splitlines()[0].strip()
    return first or text


def build_telegram_message(payload: dict[str, Any], *, event: str) -> str:
    """Build a short HTML Telegram message for pipeline / legacy refresh events."""
    pipeline = str(payload.get("pipeline") or "job")
    errors = payload.get("errors") or []
    raw_err = str(errors[0] if errors else payload.get("error") or "")
    # Prefer FAIL labels so deploy_failed is not drowned by OK verify tails.
    err = _clip(_prefer_fail_summary(raw_err), 140)

    # --- Discover family ---
    if event == "discover_done":
        queued = int(payload.get("queued_count") or 0)
        batches = payload.get("estimated_download_batches")
        disc = payload.get("discovery") or {}
        total = disc.get("total") if isinstance(disc, dict) else None
        q_new = payload.get("queued_new")
        q_sync = payload.get("queued_sync")
        q_repair = payload.get("queued_repair")
        if q_new is not None and q_sync is not None and q_repair is not None:
            line2 = (
                f"Queued {queued} (new {int(q_new)} · sync {int(q_sync)} · "
                f"repair {int(q_repair)})"
            )
        else:
            line2 = f"Queued {queued} for download"
        if batches is not None:
            line2 += f" · ~{batches} batch" + ("es" if int(batches) != 1 else "") + " of 25"
        if total is not None:
            line2 += f" · found {total} live"
        return _finish(
            [_title("🔎", "Discover finished"), line2, _queue_line(payload.get("ledger"))],
            payload,
        )
    if event == "discover_empty":
        disc = payload.get("discovery") or {}
        total = disc.get("total") if isinstance(disc, dict) else None
        line2 = "Nothing new to queue for download"
        if total is not None:
            line2 += f" · scanned {total}"
        return _finish(
            [_title("🔎", "Discover finished"), line2, _queue_line(payload.get("ledger"))],
            payload,
        )
    if event == "discover_failed":
        return _finish(
            [
                _title("❌", "Discover failed"),
                err or "See full log for details",
                _queue_line(payload.get("ledger")),
            ],
            payload,
        )
    if event == "discover_retry_scheduled":
        attempt = payload.get("retry_attempt") or "?"
        wait = payload.get("wait_minutes") or "?"
        return _finish(
            [
                _title("🔁", "Discover will retry"),
                f"Attempt {attempt} · waiting {wait} minutes",
            ],
            payload,
        )
    if event == "discover_retries_exhausted":
        return _finish(
            [
                _title("🛑", "Discover retries used up"),
                "Will try again on the next 6-hour slot",
            ],
            payload,
        )

    # --- Download family ---
    if event == "download_batch_done":
        batch = payload.get("batch_number") or "?"
        ok = int(payload.get("batch_ok") or 0)
        fail = int(payload.get("batch_failed") or 0)
        flushed = int(payload.get("batch_flushed") or 0)
        left = payload.get("backlog_left")
        line2 = f"Batch {batch}: downloaded {ok}"
        if fail:
            line2 += f" · {fail} failed"
        if flushed:
            line2 += f" · +{flushed} PDFs on server"
        if left is not None:
            line2 += f" · {left} left"
        return _finish(
            [_title("⬇️", "Download batch"), line2, _queue_line(payload.get("ledger"))],
            payload,
        )
    if event == "download_done":
        ok = int(payload.get("download_ok") or 0)
        fail = int(payload.get("download_failed") or 0)
        batches = payload.get("batches_completed")
        dur = _fmt_duration(payload.get("wall_seconds"))
        left = payload.get("backlog_left")
        if ok == 0 and fail == 0:
            line2 = "Nothing new to download"
        elif ok == 0 and fail > 0:
            line2 = f"No new files · {fail} failed"
        else:
            line2 = f"Downloaded {ok} new file" + ("s" if ok != 1 else "")
            if fail:
                line2 += f" · {fail} failed"
        if batches:
            line2 += f" · {batches} batch" + ("es" if int(batches) != 1 else "")
        if left is not None and int(left) == 0:
            line2 += " · catch-up clear"
        if dur:
            line2 += f" · took {dur}"
        return _finish(
            [_title("⬇️", "Download finished"), line2, _queue_line(payload.get("ledger"))],
            payload,
        )
    if event == "download_failed":
        return _finish(
            [
                _title("❌", "Download failed"),
                err or "See full log for details",
                _queue_line(payload.get("ledger")),
            ],
            payload,
        )
    if event == "download_retry_scheduled":
        attempt = payload.get("retry_attempt") or "?"
        wait = payload.get("wait_minutes") or "?"
        return _finish(
            [
                _title("🔁", "Download will retry"),
                f"Attempt {attempt} · waiting {wait} minutes",
            ],
            payload,
        )
    if event == "download_retries_exhausted":
        return _finish(
            [
                _title("🛑", "Download retries used up"),
                "Will try again on the next 6-hour slot",
            ],
            payload,
        )

    # --- Parse ---
    if event == "parse_done":
        ok = int(payload.get("parse_ok") or 0)
        fail = int(payload.get("parse_failed") or 0)
        auctions = payload.get("auctions")
        if ok == 0 and fail == 0:
            line2 = "No auctions processed this round"
        else:
            line2 = f"Processed {ok} OK"
            if fail:
                line2 += f" · {fail} failed"
        if auctions is not None:
            line2 += f" · site list now {auctions} auctions"
        lines = [_title("🧩", "Processing finished"), line2]
        note = str(payload.get("hygiene_note") or "").strip()
        if not note and int(payload.get("dropped_aged_out") or 0) > 0:
            n = int(payload.get("dropped_aged_out") or 0)
            note = f"Removed {n} aged-out auction" + ("s" if n != 1 else "")
        if note:
            lines.append(note)
        media = payload.get("media_push") or {}
        if isinstance(media, dict) and media.get("attempted"):
            if media.get("ok"):
                lines.append("Uploaded photos/PDFs to the server")
            else:
                lines.append("Photo upload failed — will retry next drain")
        lines.append(_queue_line(payload.get("ledger")))
        return _finish(lines, payload)
    if event == "parse_failed":
        return _finish(
            [
                _title("❌", "Processing failed"),
                err or "See full log for details",
                _queue_line(payload.get("ledger")),
            ],
            payload,
        )
    if event == "quarantine_added":
        n = payload.get("quarantine_added") or "?"
        hours = payload.get("quarantine_hours") or 48
        klass = payload.get("quarantine_error_class") or "poison"
        return _finish(
            [
                _title("⚠️", "Quarantine added"),
                f"Parked {n} bad item(s) ({klass}) for {hours}h",
            ],
            payload,
        )

    # --- Deploy ---
    if event == "deploy_done":
        n = payload.get("auctions")
        if payload.get("deploy_skipped_unchanged"):
            line2 = (
                f"No change — site already has {n} auctions"
                if n is not None
                else "No change — site already up to date"
            )
            return _finish([_title("🚀", "Site update skipped"), line2], payload)
        line2 = f"Pushed {n} auctions live" if n is not None else "Live site updated"
        return _finish([_title("🚀", "Site updated"), line2], payload)
    if event == "deploy_failed":
        return _finish(
            [_title("❌", "Site update failed"), err or "See full log for details"],
            payload,
        )

    # --- Drain ---
    if event == "drain_done":
        cycles = int(payload.get("cycles_completed") or 0)
        left = payload.get("parse_backlog_end")
        if cycles == 0:
            line2 = "Nothing was waiting — already clear"
        elif cycles == 1:
            line2 = "Cleared the backlog in 1 round"
        else:
            line2 = f"Cleared the backlog in {cycles} rounds"
        if left is not None:
            left_n = int(left)
            if left_n == 0:
                line2 += " · nothing left to process"
            else:
                line2 += f" · still waiting: {left_n}"
        return _finish(
            [_title("✅", "Catch-up finished"), line2, _queue_line(payload.get("ledger"))],
            payload,
        )
    if event == "drain_stopped":
        line2 = str(payload.get("message") or "").strip()
        if line2 != "ledger pull failed":
            line2 = err or "See full log for details"
        return _finish(
            [
                _title("🛑", "Catch-up stopped"),
                line2,
                _queue_line(payload.get("ledger")),
            ],
            payload,
        )

    # --- Legacy refresh / UI deploy ---
    if event in {"success", "completed"}:
        n = payload.get("total_auctions") or payload.get("auctions")
        line2 = f"{n} auctions on site" if n is not None else "Finished OK"
        by = payload.get("by_source") or {}
        if by:
            line2 += " · " + ", ".join(f"{k}={v}" for k, v in sorted(by.items())[:4])
        return _finish([_title("✅", "Refresh finished"), line2], payload)
    if event in {"failed", "blocked"}:
        system = "Refresh" if pipeline != "deploy_ui" else "UI deploy"
        word = "failed" if event == "failed" else "blocked"
        return _finish(
            [
                _title("❌" if event == "failed" else "🚫", f"{system} {word}"),
                err or "See full log for details",
            ],
            payload,
        )

    # Quiet / unknown: still return a tiny stub (may be unused when QUIET filters)
    return _finish([_title("ℹ️", f"{pipeline.title()} · {event}")], payload)


def build_ai_enrichment_message(payload: dict[str, Any], *, event: str = "report") -> str:
    """Short AI enrichment Telegram card."""
    if event == "started":
        return _finish([_title("🤖", "AI enrichment started")], payload)
    if event == "skipped":
        reason = _clip(payload.get("error") or payload.get("skip_reason") or "skipped", 120)
        return _finish([_title("⏭️", "AI enrichment skipped"), reason], payload)
    if event == "failed":
        return _finish(
            [_title("❌", "AI enrichment failed"), _clip(payload.get("error") or "see log", 140)],
            payload,
        )

    # complete / report
    ready = payload.get("ready", 0)
    failed = payload.get("failed", 0)
    skipped = payload.get("skipped", 0)
    processed = payload.get("processed", 0)
    budget = payload.get("budget") or {}
    selection = payload.get("selection") or {}
    line2 = f"{ready} ready · {failed} failed · {skipped} skipped · {processed} ran"
    line3_parts: list[str] = []
    if budget:
        rem = budget.get("remaining_today")
        if rem is not None:
            line3_parts.append(f"budget left today: {rem}")
    rem_sel = selection.get("remaining_after_selection")
    if rem_sel is not None:
        line3_parts.append(f"still in queue: {rem_sel}")
    dur = _fmt_duration(payload.get("duration_sec"))
    if dur:
        line3_parts.append(f"took {dur}")
    lines = [
        _title("🤖", "AI enrichment finished" if event in {"complete", "report"} else f"AI · {event}"),
        line2,
    ]
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
