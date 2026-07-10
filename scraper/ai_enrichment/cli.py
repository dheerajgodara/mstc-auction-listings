"""CLI for offline-safe AI enrichment (dry-run, mock, hydrate)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from scraper.ai_enrichment.hydrate import hydrate_json_file
from scraper.ai_enrichment.queue import EnrichmentQueue, count_cache_stats
from scraper.ai_enrichment.schema import AI_SCHEMA_VERSION, PROMPT_VERSION
from scraper.config import AI_ENRICHMENT_CACHE_DIR, DEFAULT_JSON_OUT
from scraper.models import AuctionRecord
from scraper.telegram_reporter import send_ai_enrichment_report

logger = logging.getLogger(__name__)


def _load_auctions(json_path: Path) -> list[AuctionRecord]:
    if not json_path.is_file():
        raise FileNotFoundError(f"Auction export not found: {json_path}")
    export = json.loads(json_path.read_text(encoding="utf-8"))
    return [AuctionRecord.model_validate(a) for a in export.get("auctions") or []]


def cmd_enrich(args: argparse.Namespace) -> int:
    allow_network = bool(args.allow_network)
    mock = bool(args.mock or not allow_network)
    no_network = not allow_network

    auctions = _load_auctions(args.json)
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
    payload["cache_stats"] = count_cache_stats(args.cache_dir)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.telegram_report:
        send_ai_enrichment_report(payload)
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
