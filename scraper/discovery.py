from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.adapters.eauction_adapter import adapt_eauction_record
from scraper.adapters.gem_forward_adapter import adapt_gem_forward_auction
from scraper.adapters.mstc_adapter import adapt_mstc_record
from scraper.category_map import should_exclude_category
from scraper.config import GEM_FORWARD_PER_PAGE, OFFICE_CODES
from scraper.eauction_scraper import scrape_eauction_tabs
from scraper.export_guard import write_auctions_json
from scraper.filters import parse_min_closing_boundary, partition_closing_lanes
from scraper.gem_forward_client import GemForwardClient
from scraper.gem_forward_scraper import scrape_gem_forward
from scraper.main import listing_to_base
from scraper.models import AuctionRecord, AuctionsExport
from scraper.mstc_api import fetch_all_listing_api

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.discovery")

EAUCTION_TABS = ("closingTodayTab", "closingWeekTab", "closingTwoWeekTab")


def _count_by(records: list[AuctionRecord], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value = getattr(record, field, None) or "unknown"
        counter[str(value)] += 1
    return dict(counter)


def discover_mstc(
    *,
    office_codes: list[str] | None = None,
    min_closing_date: str | None = None,
) -> tuple[list[AuctionRecord], dict]:
    min_closing = parse_min_closing_boundary(min_closing_date) if min_closing_date else None
    records: list[AuctionRecord] = []
    office_counts: dict[str, int] = {}
    requested_offices = list(office_codes or OFFICE_CODES)
    fetched_offices: list[str] = []
    for office_meta, auctions in fetch_all_listing_api(office_codes=requested_offices):
        office_records = [adapt_mstc_record(listing_to_base(auction, office_meta)) for auction in auctions]
        office_code = office_meta.REGION or office_meta.OFFICE
        office_counts[office_code] = len(office_records)
        fetched_offices.append(office_code)
        records.extend(office_records)
    before = len(records)
    live, archive, lane_stats = partition_closing_lanes(records, min_closing=min_closing)
    # Upsert both live + archive shells; live runway still enforced at export.
    combined = list(live) + list(archive)
    filter_stats = {
        "before_filter": before,
        "kept": len(live),
        "excluded_past_closing": int(lane_stats.get("archive") or 0)
        + int(lane_stats.get("excluded_too_old") or 0),
        "excluded_missing_closing": int(lane_stats.get("excluded_missing_closing") or 0),
        "archive_kept": int(lane_stats.get("archive") or 0),
        "lanes": lane_stats,
    }
    return combined, {
        "source": "mstc",
        "complete": set(fetched_offices) == set(requested_offices),
        "before_filter": before,
        "requested_offices": requested_offices,
        "fetched_offices": fetched_offices,
        "failed_offices": sorted(set(requested_offices) - set(fetched_offices)),
        "office_counts": office_counts,
        "future_filter": filter_stats,
        "live_count": len(live),
        "archive_count": len(archive),
    }


def discover_gem_forward(
    *,
    min_closing_date: str | None = None,
    limit: int | None = None,
    transport: str = "auto",
) -> tuple[list[AuctionRecord], dict]:
    min_closing = parse_min_closing_boundary(min_closing_date) if min_closing_date else None
    client = GemForwardClient(transport=transport)
    auctions = scrape_gem_forward(
        client=client,
        per_page=GEM_FORWARD_PER_PAGE,
        limit=limit,
        enrich=False,
    )
    records = [
        adapt_gem_forward_auction(auction)
        for auction in auctions
    ]
    records = [r for r in records if not should_exclude_category(r.asset_category, source="gem_forward")]
    before = len(records)
    live, archive, lane_stats = partition_closing_lanes(records, min_closing=min_closing)
    combined = list(live) + list(archive)
    filter_stats = {
        "before_filter": before,
        "kept": len(live),
        "excluded_past_closing": int(lane_stats.get("archive") or 0)
        + int(lane_stats.get("excluded_too_old") or 0),
        "excluded_missing_closing": int(lane_stats.get("excluded_missing_closing") or 0),
        "archive_kept": int(lane_stats.get("archive") or 0),
        "lanes": lane_stats,
    }
    return combined, {
        "source": "gem_forward",
        "complete": limit is None,
        "before_filter": before,
        "transport": client._active_transport,
        "future_filter": filter_stats,
        "live_count": len(live),
        "archive_count": len(archive),
    }


def discover_eauction(
    *,
    min_closing_date: str | None = None,
    limit: int | None = None,
    max_pages: int | None = None,
) -> tuple[list[AuctionRecord], dict]:
    min_closing = parse_min_closing_boundary(min_closing_date) if min_closing_date else None
    rows, stats = scrape_eauction_tabs(
        tabs=list(EAUCTION_TABS),
        max_pages=max_pages,
        enrich_details=False,
        limit=limit,
    )
    records = [adapt_eauction_record(row) for row in rows]
    records = [r for r in records if not should_exclude_category(r.asset_category, source="eauction")]
    before = len(records)
    live, archive, lane_stats = partition_closing_lanes(records, min_closing=min_closing)
    combined = list(live) + list(archive)
    filter_stats = {
        "before_filter": before,
        "kept": len(live),
        "excluded_past_closing": int(lane_stats.get("archive") or 0)
        + int(lane_stats.get("excluded_too_old") or 0),
        "excluded_missing_closing": int(lane_stats.get("excluded_missing_closing") or 0),
        "archive_kept": int(lane_stats.get("archive") or 0),
        "lanes": lane_stats,
    }
    return combined, {
        **stats,
        "source": "eauction",
        "complete": limit is None and max_pages is None,
        "before_filter": before,
        "future_filter": filter_stats,
        "live_count": len(live),
        "archive_count": len(archive),
    }


def run_discovery(
    *,
    sources: list[str],
    out_path: Path,
    min_closing_date: str | None,
    mstc_offices: list[str] | None = None,
    gem_limit: int | None = None,
    gem_transport: str = "auto",
    eauction_limit: int | None = None,
    eauction_max_pages: int | None = None,
    allow_small_output: bool = False,
) -> AuctionsExport:
    records: list[AuctionRecord] = []
    source_stats: dict[str, dict] = {}

    if "mstc" in sources:
        mstc_records, stats = discover_mstc(office_codes=mstc_offices, min_closing_date=min_closing_date)
        records.extend(mstc_records)
        source_stats["mstc"] = stats
    if "gem_forward" in sources:
        gem_records, stats = discover_gem_forward(
            min_closing_date=min_closing_date,
            limit=gem_limit,
            transport=gem_transport,
        )
        records.extend(gem_records)
        source_stats["gem_forward"] = stats
    if "eauction" in sources:
        eauction_records, stats = discover_eauction(
            min_closing_date=min_closing_date,
            limit=eauction_limit,
            max_pages=eauction_max_pages,
        )
        records.extend(eauction_records)
        source_stats["eauction"] = stats

    records.sort(key=lambda r: r.closing or datetime.min.replace(tzinfo=IST))
    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(records),
        auctions=records,
        stats={
            "discovery_only": True,
            "min_closing_date": min_closing_date,
            "by_source": _count_by(records, "source"),
            "by_category": _count_by(records, "asset_category"),
            "source_stats": source_stats,
            "live_count": sum(int(s.get("live_count") or 0) for s in source_stats.values()),
            "archive_count": sum(int(s.get("archive_count") or 0) for s in source_stats.values()),
        },
    )
    write_auctions_json(out_path, export.model_dump(mode="json"), allow_small_output=allow_small_output)
    logger.info("Discovery wrote %d records -> %s", export.count, out_path)
    return export


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Run shallow auction discovery without deep PDF/detail parsing.")
    parser.add_argument("--sources", default="mstc,gem_forward,eauction")
    parser.add_argument("--out", type=Path, default=Path("work/discovery_latest.json"))
    parser.add_argument("--min-closing-date")
    parser.add_argument("--mstc-offices", help="Comma-separated MSTC offices for smoke tests")
    parser.add_argument("--gem-limit", type=int)
    parser.add_argument("--gem-transport", choices=("auto", "direct", "ssh"), default="auto")
    parser.add_argument("--eauction-limit", type=int)
    parser.add_argument("--eauction-max-pages", type=int)
    parser.add_argument("--allow-small-output", action="store_true")
    args = parser.parse_args(argv)

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    offices = [s.strip().upper() for s in args.mstc_offices.split(",") if s.strip()] if args.mstc_offices else None
    run_discovery(
        sources=sources,
        out_path=args.out,
        min_closing_date=args.min_closing_date,
        mstc_offices=offices,
        gem_limit=args.gem_limit,
        gem_transport=args.gem_transport,
        eauction_limit=args.eauction_limit,
        eauction_max_pages=args.eauction_max_pages,
        allow_small_output=args.allow_small_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
