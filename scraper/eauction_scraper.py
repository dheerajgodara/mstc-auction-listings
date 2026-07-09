from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from scraper.eauction_client import CLOSING_TABS, EauctionClient
from scraper.eauction_parser import parse_detail_page, parse_listing_rows

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


class EauctionExport(BaseModel):
    generated_at: datetime
    source: str = "eauction"
    count: int
    auctions: list[dict[str, Any]]
    stats: dict[str, Any] = Field(default_factory=dict)


def _fetch_all_pages(
    cli: EauctionClient,
    html: str,
    rows: list[dict[str, Any]],
    *,
    max_pages: int | None,
    delay_sec: float,
) -> int:
    pages_fetched = 1
    seen = {f"{r.get('auction_id')}::{r.get('title')}" for r in rows}
    pagination_links = cli.discover_pagination_links(html)
    page_links = pagination_links if max_pages in (None, 0) else pagination_links[: max(0, max_pages - 1)]

    for link in page_links:
        time.sleep(delay_sec)
        _, page_html, _ = cli.fetch_pagination_page(link["href"])
        pages_fetched += 1
        for row in parse_listing_rows(page_html):
            key = f"{row.get('auction_id')}::{row.get('title')}"
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return pages_fetched


def scrape_eauction(
    *,
    client: EauctionClient | None = None,
    limit: int | None = None,
    enrich_details: bool = False,
    delay_sec: float = 0.75,
    tab: str = "closingWeekTab",
    max_pages: int | None = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if tab not in CLOSING_TABS:
        raise ValueError(f"Invalid tab {tab!r}; choose from {CLOSING_TABS}")

    cli = client or EauctionClient()
    status, html, final_url = cli.fetch_listing_page(tab=tab)
    blockers = cli.detect_blockers(html)
    rows = parse_listing_rows(html)
    pages_fetched = 1

    stats: dict[str, Any] = {
        "status": "blocked" if blockers and not rows else ("ok" if rows else "empty"),
        "status_code": status,
        "final_url": final_url,
        "blocked": bool(blockers and not rows),
        "blockers": blockers,
        "captcha_blocker_count": 1 if "captcha" in blockers else 0,
        "listing_rows": len(rows),
        "tab": tab,
        "pages_fetched": pages_fetched,
        "detail_success": 0,
        "detail_fail": 0,
        "detail_skipped": 0,
        "detail_accessible": False,
    }

    if blockers and not rows:
        stats["reason"] = ",".join(blockers)
        logger.warning("eAuction blocked: %s", blockers)
        return [], stats

    if max_pages is None or max_pages != 1:
        pages_fetched = _fetch_all_pages(
            cli, html, rows, max_pages=max_pages, delay_sec=delay_sec
        )
        stats["pages_fetched"] = pages_fetched
        stats["listing_rows"] = len(rows)

    if limit is not None:
        rows = rows[:limit]

    if enrich_details and rows:
        enriched: list[dict[str, Any]] = []
        for row in rows:
            detail_url = row.get("detail_url")
            if not detail_url:
                stats["detail_skipped"] += 1
                enriched.append(row)
                continue
            try:
                time.sleep(delay_sec)
                detail_status, detail_html = cli.fetch_detail_page(detail_url)
                detail_blockers = cli.detect_blockers(detail_html)
                if detail_status == 200 and not detail_blockers:
                    enriched.append(parse_detail_page(detail_html, row))
                    stats["detail_success"] += 1
                    if not stats["detail_accessible"]:
                        stats["detail_accessible"] = True
                else:
                    enriched.append(row)
                    stats["detail_fail"] += 1
            except Exception as exc:
                logger.warning("Detail fetch failed for %s: %s", row.get("auction_id"), exc)
                enriched.append(row)
                stats["detail_fail"] += 1
        rows = enriched

    stats["exported"] = len(rows)
    stats["status"] = "ok"
    stats["blocked"] = False
    return rows, stats


def scrape_eauction_tabs(
    *,
    tabs: list[str] | None = None,
    client: EauctionClient | None = None,
    limit: int | None = None,
    enrich_details: bool = False,
    delay_sec: float = 0.75,
    max_pages: int | None = None,
    include_auction_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scrape multiple ByDate tabs, dedupe by auction_id+title, optional detail enrichment."""
    selected_tabs = tabs or ["closingWeekTab", "closingTwoWeekTab", "closingTodayTab"]
    cli = client or EauctionClient()
    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    combined_stats: dict[str, Any] = {
        "tabs": selected_tabs,
        "tabs_fetched": [],
        "pages_fetched": 0,
        "listing_rows": 0,
        "detail_success": 0,
        "detail_fail": 0,
        "detail_skipped": 0,
        "detail_accessible": False,
        "captcha_blocker_count": 0,
        "blockers": [],
        "blocked": False,
        "status": "ok",
    }

    for tab in selected_tabs:
        if tab not in CLOSING_TABS:
            raise ValueError(f"Invalid tab {tab!r}; choose from {CLOSING_TABS}")
        rows, tab_stats = scrape_eauction(
            client=cli,
            tab=tab,
            max_pages=max_pages,
            enrich_details=False,
            delay_sec=delay_sec,
            limit=None,
        )
        combined_stats["tabs_fetched"].append(
            {
                "tab": tab,
                "listing_rows": tab_stats.get("listing_rows", 0),
                "pages_fetched": tab_stats.get("pages_fetched", 0),
                "status": tab_stats.get("status"),
                "blockers": tab_stats.get("blockers", []),
            }
        )
        combined_stats["pages_fetched"] += tab_stats.get("pages_fetched", 0)
        if tab_stats.get("captcha_blocker_count"):
            combined_stats["captcha_blocker_count"] += tab_stats["captcha_blocker_count"]
        if tab_stats.get("blockers"):
            combined_stats["blockers"] = list(
                set(combined_stats["blockers"]) | set(tab_stats["blockers"])
            )
        for row in rows:
            key = f"{row.get('auction_id')}::{row.get('title')}"
            if key not in seen:
                seen.add(key)
                all_rows.append(row)
        time.sleep(delay_sec)

    combined_stats["listing_rows"] = len(all_rows)

    if include_auction_ids is not None:
        before_work_plan_filter = len(all_rows)
        all_rows = [row for row in all_rows if str(row.get("auction_id") or "") in include_auction_ids]
        combined_stats["excluded_not_in_work_plan"] = before_work_plan_filter - len(all_rows)

    if limit is not None:
        all_rows = all_rows[:limit]

    if enrich_details and all_rows:
        enriched: list[dict[str, Any]] = []
        for row in all_rows:
            detail_url = row.get("detail_url")
            if not detail_url:
                combined_stats["detail_skipped"] += 1
                enriched.append(row)
                continue
            try:
                time.sleep(delay_sec)
                detail_status, detail_html = cli.fetch_detail_page(detail_url)
                detail_blockers = cli.detect_blockers(detail_html)
                if detail_status == 200 and not detail_blockers:
                    enriched.append(parse_detail_page(detail_html, row))
                    combined_stats["detail_success"] += 1
                    combined_stats["detail_accessible"] = True
                else:
                    enriched.append(row)
                    combined_stats["detail_fail"] += 1
            except Exception as exc:
                logger.warning("Detail fetch failed for %s: %s", row.get("auction_id"), exc)
                enriched.append(row)
                combined_stats["detail_fail"] += 1
        all_rows = enriched

    combined_stats["exported"] = len(all_rows)
    if combined_stats["blockers"] and not all_rows:
        combined_stats["status"] = "blocked"
        combined_stats["blocked"] = True
    return all_rows, combined_stats


def run_export(
    *,
    out_path: Path,
    tab: str = "closingWeekTab",
    max_pages: int = 7,
    limit: int | None = 50,
    enrich_details: bool = True,
    delay_sec: float = 0.75,
) -> EauctionExport:
    rows, stats = scrape_eauction(
        tab=tab,
        max_pages=max_pages,
        limit=limit,
        enrich_details=enrich_details,
        delay_sec=delay_sec,
    )
    export = EauctionExport(
        generated_at=datetime.now(IST),
        count=len(rows),
        auctions=rows,
        stats=stats,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(export.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Wrote %d eAuction records to %s (pages=%s detail_ok=%s detail_fail=%s)",
        export.count,
        out_path,
        stats.get("pages_fetched"),
        stats.get("detail_success"),
        stats.get("detail_fail"),
    )
    return export


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Scrape eAuction.gov.in public ByDate listings")
    parser.add_argument(
        "--tab",
        choices=CLOSING_TABS,
        default="closingWeekTab",
        help="Closing-date tab (no captcha)",
    )
    parser.add_argument("--max-pages", type=int, default=7)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--enrich-details", action="store_true", default=False)
    parser.add_argument("--out", type=Path, default=Path("work/eauction_export.json"))
    parser.add_argument("--delay-sec", type=float, default=0.75)
    args = parser.parse_args(argv)

    try:
        export = run_export(
            out_path=args.out,
            tab=args.tab,
            max_pages=args.max_pages,
            limit=args.limit,
            enrich_details=args.enrich_details,
            delay_sec=args.delay_sec,
        )
        if export.stats.get("blocked"):
            return 2
        return 0
    except Exception as exc:
        logger.exception("eAuction scrape failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
