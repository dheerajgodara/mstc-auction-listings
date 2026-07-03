from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.adapters.eauction_adapter import adapt_eauction_record
from scraper.adapters.gem_forward_adapter import adapt_gem_forward_auction
from scraper.adapters.mstc_adapter import adapt_mstc_record
from scraper.category_map import should_exclude_category
from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_JSON_OUT,
    DEFAULT_PDF_DIR,
    DEFAULT_THUMBS_DIR,
)
from scraper.export_guard import write_auctions_json
from scraper.eauction_scraper import scrape_eauction_tabs
from scraper.filters import apply_future_filter, parse_min_closing_date
from scraper.gem_forward_client import GemForwardTransportError
from scraper.gem_forward_scraper import scrape_gem_forward
from scraper.main import run_pipeline
from scraper.models import AuctionRecord, AuctionsExport

IST = ZoneInfo("Asia/Kolkata")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scraper.run_all")

EAUCTION_DEFAULT_TABS = ("closingTodayTab", "closingWeekTab", "closingTwoWeekTab")


def _count_by(records: list[AuctionRecord], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value = getattr(record, field, None) or "unknown"
        counter[str(value)] += 1
    return dict(counter)


def _dedupe_records(records: list[AuctionRecord]) -> list[AuctionRecord]:
    seen: set[str] = set()
    unique: list[AuctionRecord] = []
    for record in records:
        if record.id in seen:
            continue
        seen.add(record.id)
        unique.append(record)
    return unique


def _closing_bounds(records: list[AuctionRecord]) -> dict[str, str | None]:
    closings = [r.closing for r in records if r.closing]
    if not closings:
        return {"earliest": None, "latest": None}
    closings.sort()
    return {
        "earliest": closings[0].isoformat(),
        "latest": closings[-1].isoformat(),
    }


def _quality_stats(records: list[AuctionRecord]) -> dict:
    confidence = Counter(r.parse_confidence for r in records)
    price_status = Counter(r.price_parse_status for r in records)
    emd_status = Counter(r.emd_parse_status for r in records)
    return {
        "confidence": dict(confidence),
        "price_parse_status": dict(price_status),
        "emd_parse_status": dict(emd_status),
        "missing_seller": sum(1 for r in records if not r.seller),
        "missing_location": sum(1 for r in records if not r.location),
        "missing_closing": sum(1 for r in records if not r.closing),
        "missing_lots": sum(1 for r in records if not r.lots),
        "missing_price": sum(1 for r in records if r.price_parse_status == "missing"),
        "missing_emd": sum(1 for r in records if r.emd_parse_status == "missing"),
        "low_minimal_confidence": confidence.get("low", 0) + confidence.get("minimal", 0),
    }


def run_mstc_source(
    *,
    out_path: Path,
    pdf_dir: Path,
    docs_dir: Path,
    thumbs_dir: Path,
    limit: int | None,
    max_docs_per_run: int,
    min_closing_date: str | None,
) -> tuple[list[AuctionRecord], dict]:
    export = run_pipeline(
        out_path=out_path,
        pdf_dir=pdf_dir,
        docs_dir=docs_dir,
        thumbs_dir=thumbs_dir,
        limit=limit,
        max_docs_per_run=max_docs_per_run,
        min_closing_date=min_closing_date,
    )
    records = [adapt_mstc_record(r) for r in export.auctions]
    return records, dict(export.stats)


def run_gem_forward_source(
    *,
    limit: int | None,
    enrich: bool = True,
) -> tuple[list[AuctionRecord], dict]:
    stats: dict = {"found_before_filter": 0, "enrich_success": 0, "enrich_fail": 0}
    try:
        auctions = scrape_gem_forward(limit=limit, enrich=enrich)
        stats["found_before_filter"] = len(auctions)
        records = [adapt_gem_forward_auction(a) for a in auctions]
        if enrich:
            stats["enrich_success"] = sum(1 for a in auctions if a.items or a.auction_brief)
            stats["enrich_fail"] = len(auctions) - stats["enrich_success"]
        records = [
            r for r in records if not should_exclude_category(r.asset_category, source="gem_forward")
        ]
        stats["with_price"] = sum(
            1 for r in records if r.min_start_price is not None or r.price_parse_status == "numeric"
        )
        stats["with_emd"] = sum(1 for r in records if r.pre_bid_emd_amount is not None)
        stats["with_document_urls"] = sum(1 for r in records if r.document_urls)
        stats["exported"] = len(records)
        return records, stats
    except GemForwardTransportError as exc:
        logger.warning("GeM Forward skipped: %s", exc)
        stats["error"] = str(exc)
        return [], stats
    except Exception as exc:
        logger.warning("GeM Forward failed: %s", exc)
        stats["error"] = str(exc)
        return [], stats


def run_eauction_source(
    *,
    limit: int | None,
    tabs: tuple[str, ...] = EAUCTION_DEFAULT_TABS,
    max_pages: int | None = None,
    enrich_details: bool = True,
    delay_sec: float = 0.75,
) -> tuple[list[AuctionRecord], dict]:
    try:
        rows, stats = scrape_eauction_tabs(
            tabs=list(tabs),
            limit=limit,
            max_pages=max_pages,
            enrich_details=enrich_details,
            delay_sec=delay_sec,
        )
        stats["found_before_filter"] = stats.get("listing_rows", len(rows))
        records = [adapt_eauction_record(row) for row in rows]
        records = [
            r for r in records if not should_exclude_category(r.asset_category, source="eauction")
        ]
        stats["with_price"] = sum(
            1 for r in records if r.min_start_price is not None or r.price_parse_status == "numeric"
        )
        stats["with_emd"] = sum(1 for r in records if r.pre_bid_emd_amount is not None)
        stats["with_document_urls"] = sum(1 for r in records if r.document_urls)
        stats["exported"] = len(records)
        stats["adapted"] = len(records)
        return records, stats
    except Exception as exc:
        logger.warning("eAuction failed: %s", exc)
        return [], {"error": str(exc), "status": "error"}


def run_all(
    *,
    sources: list[str],
    out_path: Path,
    pdf_dir: Path,
    docs_dir: Path,
    thumbs_dir: Path,
    limit: int | None = None,
    no_global_limit: bool = False,
    mstc_limit: int | None = None,
    eauction_limit: int | None = None,
    gem_forward_limit: int | None = None,
    max_docs_per_run: int = 100,
    min_closing_date: str | None = None,
    eauction_tabs: tuple[str, ...] = EAUCTION_DEFAULT_TABS,
    eauction_max_pages: int | None = None,
    eauction_enrich_details: bool = True,
    allow_small_output: bool = False,
) -> AuctionsExport:
    all_records: list[AuctionRecord] = []
    failures_by_source: dict[str, str] = {}
    source_stats: dict[str, dict] = {}
    filter_stats: dict[str, int] = {}

    if no_global_limit:
        effective_mstc_limit = mstc_limit
        effective_ea_limit = eauction_limit
        effective_gem_limit = gem_forward_limit
    else:
        effective_mstc_limit = mstc_limit if mstc_limit is not None else limit
        effective_ea_limit = eauction_limit if eauction_limit is not None else limit
        effective_gem_limit = gem_forward_limit if gem_forward_limit is not None else limit

    min_closing = parse_min_closing_date(min_closing_date) if min_closing_date else None

    if "mstc" in sources:
        logger.info("Running MSTC source (limit=%s min_closing=%s)", effective_mstc_limit, min_closing_date)
        mstc_records, mstc_stats = run_mstc_source(
            out_path=out_path,
            pdf_dir=pdf_dir,
            docs_dir=docs_dir,
            thumbs_dir=thumbs_dir,
            limit=effective_mstc_limit,
            max_docs_per_run=max_docs_per_run,
            min_closing_date=min_closing_date,
        )
        all_records.extend(mstc_records)
        source_stats["mstc"] = mstc_stats
        if mstc_stats.get("error"):
            failures_by_source["mstc"] = str(mstc_stats["error"])

    if "gem_forward" in sources:
        logger.info("Running GeM Forward source (limit=%s)", effective_gem_limit)
        gem_records, gem_stats = run_gem_forward_source(limit=effective_gem_limit, enrich=True)
        all_records.extend(gem_records)
        source_stats["gem_forward"] = gem_stats
        if gem_stats.get("error"):
            failures_by_source["gem_forward"] = str(gem_stats["error"])

    if "eauction" in sources:
        logger.info(
            "Running eAuction source (limit=%s tabs=%s max_pages=%s)",
            effective_ea_limit,
            ",".join(eauction_tabs),
            eauction_max_pages,
        )
        ea_records, ea_stats = run_eauction_source(
            limit=effective_ea_limit,
            tabs=eauction_tabs,
            max_pages=eauction_max_pages,
            enrich_details=eauction_enrich_details,
        )
        all_records.extend(ea_records)
        source_stats["eauction"] = ea_stats
        if ea_stats.get("error"):
            failures_by_source["eauction"] = str(ea_stats["error"])
        elif ea_stats.get("blocked") or ea_stats.get("status") == "blocked":
            failures_by_source["eauction"] = ea_stats.get("reason") or ",".join(
                ea_stats.get("blockers") or ["blocked"]
            )

    before_filter_count = len(all_records)
    all_records, filter_stats = apply_future_filter(all_records, min_closing)
    all_records = _dedupe_records(all_records)
    all_records.sort(key=lambda r: r.closing or datetime.min.replace(tzinfo=IST))

    documents_stats = source_stats.get("mstc", {}).get("documents", {})
    quality = _quality_stats(all_records)
    stats = {
        "by_source": _count_by(all_records, "source"),
        "by_category": _count_by(all_records, "asset_category"),
        "by_state": _count_by(all_records, "state"),
        "failures_by_source": failures_by_source,
        "documents": documents_stats,
        "mstc": source_stats.get("mstc", {}),
        "eauction": source_stats.get("eauction", {}),
        "gem_forward": source_stats.get("gem_forward", {}),
        "sources_requested": sources,
        "auctions_parsed": len(all_records),
        "total_lots_in_export": sum(len(r.lots) for r in all_records),
        "auctions_before_future_filter": before_filter_count,
        "future_filter": filter_stats,
        "min_closing_date": min_closing_date,
        "closing_bounds": _closing_bounds(all_records),
        "quality": quality,
        "limits": {
            "mstc": effective_mstc_limit,
            "eauction": effective_ea_limit,
            "gem_forward": effective_gem_limit,
            "global": limit,
            "no_global_limit": no_global_limit,
        },
    }

    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(all_records),
        auctions=all_records,
        stats=stats,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_auctions_json(
        out_path,
        export.model_dump(mode="json"),
        allow_small_output=allow_small_output,
    )

    logger.info(
        "run_all complete: auctions=%d lots=%d sources=%s by_source=%s",
        export.count,
        stats["total_lots_in_export"],
        ",".join(sources),
        stats["by_source"],
    )
    return export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run multi-source auction scraper orchestrator")
    parser.add_argument(
        "--sources",
        type=str,
        default="mstc",
        help="Comma-separated sources: mstc,eauction,gem_forward",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--thumbs-dir", type=Path, default=DEFAULT_THUMBS_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Global fallback limit per source")
    parser.add_argument("--no-global-limit", action="store_true", help="No global cap; per-source limits only")
    parser.add_argument("--mstc-limit", type=int, default=None)
    parser.add_argument("--eauction-limit", type=int, default=None)
    parser.add_argument("--gem-forward-limit", type=int, default=None)
    parser.add_argument("--max-docs-per-run", type=int, default=100)
    parser.add_argument(
        "--min-closing-date",
        type=str,
        default=None,
        help="Keep auctions closing on/after YYYY-MM-DD 00:00 IST",
    )
    parser.add_argument(
        "--eauction-tabs",
        type=str,
        default=",".join(EAUCTION_DEFAULT_TABS),
        help="Comma-separated eAuction tabs",
    )
    parser.add_argument(
        "--eauction-max-pages",
        type=int,
        default=None,
        help="Max pages per eAuction tab (default: all pages)",
    )
    parser.add_argument("--eauction-no-enrich", action="store_true")
    parser.add_argument(
        "--allow-small-output",
        action="store_true",
        help="Allow writing fewer than 100 auctions to protected production JSON paths",
    )
    args = parser.parse_args(argv)

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    if not sources:
        logger.error("No sources specified")
        return 1

    eauction_tabs = tuple(t.strip() for t in args.eauction_tabs.split(",") if t.strip())

    try:
        export = run_all(
            sources=sources,
            out_path=args.out,
            pdf_dir=args.pdf_dir,
            docs_dir=args.docs_dir,
            thumbs_dir=args.thumbs_dir,
            limit=args.limit,
            no_global_limit=args.no_global_limit,
            mstc_limit=args.mstc_limit,
            eauction_limit=args.eauction_limit,
            gem_forward_limit=args.gem_forward_limit,
            max_docs_per_run=args.max_docs_per_run,
            min_closing_date=args.min_closing_date,
            eauction_tabs=eauction_tabs,
            eauction_max_pages=args.eauction_max_pages,
            eauction_enrich_details=not args.eauction_no_enrich,
            allow_small_output=args.allow_small_output,
        )
        logger.info("Stats: %s", json.dumps(export.stats, default=str)[:1200])
        return 0
    except Exception as exc:
        logger.exception("run_all failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
