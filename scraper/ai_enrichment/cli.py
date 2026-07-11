"""CLI for offline-safe AI enrichment (dry-run, mock, hydrate)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from scraper.ai_enrichment.hydrate import hydrate_json_file
from scraper.ai_enrichment.ledger_sync import pull_remote_daily_usage, push_remote_daily_usage
from scraper.ai_enrichment.queue import EnrichmentQueue, count_cache_stats, daily_budget_state, select_priority_auctions
from scraper.ai_enrichment.schema import AI_SCHEMA_VERSION, PROMPT_VERSION
from scraper.config import AI_ENRICHMENT_CACHE_DIR, DEFAULT_JSON_OUT
from scraper.models import AuctionRecord
from scraper.telegram_reporter import send_ai_enrichment_report

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def _github_run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def _base_payload(args: argparse.Namespace, *, allow_network: bool, started_at: str) -> dict[str, object]:
    return {
        "run_id": os.environ.get("GITHUB_RUN_ID") or datetime.now(IST).strftime("%Y%m%d_%H%M%S_IST"),
        "started_at": started_at,
        "slot_ist": os.environ.get("AI_SLOT_IST"),
        "allow_network": allow_network,
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "limit": args.limit,
        "daily_budget_requested": args.daily_budget,
        "github_run_url": _github_run_url(),
    }


def _load_auctions(json_path: Path) -> list[AuctionRecord]:
    if not json_path.is_file():
        raise FileNotFoundError(f"Auction export not found: {json_path}")
    export = json.loads(json_path.read_text(encoding="utf-8"))
    return [AuctionRecord.model_validate(a) for a in export.get("auctions") or []]


def cmd_enrich(args: argparse.Namespace) -> int:
    started = time.monotonic()
    started_at = datetime.now(IST).isoformat()
    allow_network = bool(args.allow_network)
    from scraper.config import OPENROUTER_API_KEY

    # Fail closed: --allow-network without a key must not silently fall back to mock.
    if allow_network and not args.mock and not args.dry_run and not OPENROUTER_API_KEY:
        payload = {
            **_base_payload(args, allow_network=allow_network, started_at=started_at),
            "processed": 0,
            "ready": 0,
            "skipped": 0,
            "rejected": 0,
            "failed": 0,
            "error": "OPENROUTER_API_KEY missing while --allow-network was set",
            "will_call_provider": False,
            "cache_stats": count_cache_stats(args.cache_dir),
            "finished_at": datetime.now(IST).isoformat(),
        }
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if args.telegram_report:
            send_ai_enrichment_report(payload, event="failed")
        print(json.dumps(payload, indent=2))
        return 2

    mock = bool(args.mock or not allow_network)
    # Never treat mock as a successful live production enrichment for durable ledger.
    if mock and args.ledger_sync == "hostinger" and not args.dry_run:
        payload = {
            **_base_payload(args, allow_network=allow_network, started_at=started_at),
            "processed": 0,
            "ready": 0,
            "skipped": 0,
            "rejected": 0,
            "failed": 0,
            "error": "refusing hostinger ledger sync in mock/no-network mode",
            "mock": True,
            "will_call_provider": False,
            "cache_stats": count_cache_stats(args.cache_dir),
            "finished_at": datetime.now(IST).isoformat(),
        }
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if args.telegram_report:
            send_ai_enrichment_report(payload, event="failed")
        print(json.dumps(payload, indent=2))
        return 2

    no_network = not allow_network
    base_payload = _base_payload(args, allow_network=allow_network, started_at=started_at)

    if args.telegram_report:
        send_ai_enrichment_report(
            {
                **base_payload,
                "processed": 0,
                "ready": 0,
                "skipped": 0,
                "rejected": 0,
                "failed": 0,
                "budget": daily_budget_state(cache_dir=args.cache_dir, daily_budget=args.daily_budget),
                "cache_stats": count_cache_stats(args.cache_dir),
            },
            event="started",
        )

    ledger_sync_events: list[dict[str, object]] = []
    if args.ledger_sync == "hostinger" and allow_network and not args.dry_run:
        pull = pull_remote_daily_usage(args.cache_dir)
        ledger_sync_events.append(pull.to_dict())
        if not pull.ok and not args.allow_local_ledger_fallback:
            payload = {
                **base_payload,
                "processed": 0,
                "ready": 0,
                "skipped": 0,
                "rejected": 0,
                "failed": 0,
                "allow_network": allow_network,
                "will_call_provider": False,
                "ledger_sync": ledger_sync_events,
                "error": "remote_ledger_pull_failed",
                "cache_stats": count_cache_stats(args.cache_dir),
            }
            if args.report_json:
                args.report_json.parent.mkdir(parents=True, exist_ok=True)
                args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            if args.telegram_report:
                send_ai_enrichment_report(payload, event="failed")
            print(json.dumps(payload, indent=2))
            return 2

    auctions = _load_auctions(args.json)
    budget_before = daily_budget_state(cache_dir=args.cache_dir, daily_budget=args.daily_budget)
    effective_limit = args.limit
    if not args.dry_run:
        remaining_today = int(budget_before.get("remaining_today", 0) or 0)
        effective_limit = remaining_today if effective_limit is None else min(int(effective_limit), remaining_today)
    selected_pairs, selection_summary = select_priority_auctions(
        auctions,
        cache_dir=args.cache_dir,
        limit=effective_limit,
    )
    selection_payload = {
        **base_payload,
        "processed": 0,
        "ready": 0,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
        "allow_network": allow_network,
        "will_call_provider": bool(allow_network and not mock and not args.dry_run and selected_pairs),
        "selection": selection_summary,
        "budget": budget_before,
        "cache_stats": count_cache_stats(args.cache_dir),
        "ledger_sync": ledger_sync_events,
    }
    if args.telegram_report:
        event = "skipped" if not selected_pairs else "selection_done"
        send_ai_enrichment_report(selection_payload, event=event)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        plan_path = args.report_json.with_name(args.report_json.stem + ".plan.json")
        plan_path.write_text(json.dumps(selection_payload, indent=2) + "\n", encoding="utf-8")

    if not selected_pairs:
        payload = {
            **selection_payload,
            "finished_at": datetime.now(IST).isoformat(),
            "duration_sec": round(time.monotonic() - started, 2),
        }
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0

    queue = EnrichmentQueue(
        dry_run=args.dry_run,
        mock=mock,
        no_network=no_network,
        allow_network=allow_network,
        max_requests=args.limit,
        cache_dir=args.cache_dir,
        daily_budget=args.daily_budget,
    )
    report = queue.run(
        auctions,
        auction_id=args.auction_id,
        limit=args.limit,
    )
    payload = report.to_dict()
    payload.update(base_payload)
    payload["finished_at"] = datetime.now(IST).isoformat()
    payload["duration_sec"] = round(time.monotonic() - started, 2)
    payload["cache_stats"] = count_cache_stats(args.cache_dir)
    if args.ledger_sync == "hostinger" and allow_network and not args.dry_run:
        push = push_remote_daily_usage(args.cache_dir)
        ledger_sync_events.append(push.to_dict())
        payload["ledger_sync"] = ledger_sync_events
        if not push.ok and not args.allow_local_ledger_fallback:
            payload["error"] = "remote_ledger_push_failed"
            if args.report_json:
                args.report_json.parent.mkdir(parents=True, exist_ok=True)
                args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            if args.telegram_report:
                send_ai_enrichment_report(payload, event="failed")
            print(json.dumps(payload, indent=2))
            return 3
    elif ledger_sync_events:
        payload["ledger_sync"] = ledger_sync_events
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.telegram_report:
        send_ai_enrichment_report(payload, event="complete" if not payload.get("error") else "failed")
    print(json.dumps(payload, indent=2))
    return 0


def cmd_hydrate(args: argparse.Namespace) -> int:
    result = hydrate_json_file(
        args.json,
        cache_dir=args.cache_dir,
        write=not args.dry_run,
    )
    result["dry_run"] = bool(args.dry_run)
    result["prompt_version"] = PROMPT_VERSION
    result["schema_version"] = AI_SCHEMA_VERSION
    print(json.dumps(result, indent=2))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    stats = count_cache_stats(args.cache_dir)
    stats["prompt_version"] = PROMPT_VERSION
    stats["schema_version"] = AI_SCHEMA_VERSION
    print(json.dumps(stats, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI enrichment for buyer-facing headings, summaries, locations, and tags",
    )
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_OUT, help="Auctions export JSON")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=AI_ENRICHMENT_CACHE_DIR,
        help="AI enrichment cache directory",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enrich = sub.add_parser("enrich", help="Run enrichment (network-safe by default)")
    enrich.add_argument("--dry-run", action="store_true", help="Print payload stats only; no provider calls")
    enrich.add_argument("--mock", action="store_true", help="Use mock provider (default when network disabled)")
    enrich.add_argument(
        "--no-network",
        action="store_true",
        help="Alias for network-safe mode (default unless --allow-network)",
    )
    enrich.add_argument(
        "--allow-network",
        action="store_true",
        help="Opt in to live OpenRouter calls (requires OPENROUTER_API_KEY)",
    )
    enrich.add_argument("--auction-id", default=None, help="Target one auction id/number")
    enrich.add_argument("--limit", type=int, default=None, help="Max auctions/requests")
    enrich.add_argument("--daily-budget", type=int, default=950, help="Max provider calls per IST day")
    enrich.add_argument(
        "--ledger-sync",
        choices=("none", "hostinger"),
        default="none",
        help="Durable daily usage ledger backend. hostinger fails closed on sync errors.",
    )
    enrich.add_argument(
        "--allow-local-ledger-fallback",
        action="store_true",
        help="Continue with local ledger if remote sync fails. Not recommended for production.",
    )
    enrich.add_argument("--report-json", type=Path, default=None, help="Write run report JSON")
    enrich.add_argument("--telegram-report", action="store_true", help="Send Telegram summary when finished")
    enrich.set_defaults(func=cmd_enrich)

    hydrate = sub.add_parser("hydrate", help="Merge cached AI into auctions.json")
    hydrate.add_argument("--dry-run", action="store_true", help="Report only; do not write JSON")
    hydrate.set_defaults(func=cmd_hydrate)

    stats = sub.add_parser("stats", help="Show cache status counts")
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        logger.exception("ai_enrichment CLI failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
