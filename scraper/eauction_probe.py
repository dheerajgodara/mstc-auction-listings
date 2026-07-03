from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin

from scraper.eauction_client import EAUCTION_BASE, EAUCTION_LISTING_PATH, EauctionClient
from scraper.eauction_parser import parse_detail_page, parse_listing_rows

logger = logging.getLogger("scraper.eauction_probe")


def run_probe(*, out_path: Path, fetch_detail: bool = False, tab: str | None = None) -> dict:
    client = EauctionClient()
    status, html, final_url = client.fetch_listing_page(tab=tab)
    blockers = client.detect_blockers(html)
    rows = parse_listing_rows(html)
    tabs = client.discover_closing_tabs(html)
    pagination = client.discover_pagination_links(html)

    detail_accessible = False
    detail_status = None
    if fetch_detail and rows:
        first = rows[0]
        detail_url = first.get("detail_url")
        if detail_url:
            detail_status, detail_html = client.fetch_detail_page(detail_url)
            detail_blockers = client.detect_blockers(detail_html)
            detail_accessible = detail_status == 200 and not detail_blockers
            if detail_accessible:
                rows[0] = parse_detail_page(detail_html, first)

    if blockers and rows:
        result_status = "partial"
        reason = ",".join(blockers)
    elif blockers:
        result_status = "blocked"
        reason = ",".join(blockers)
    elif rows:
        result_status = "ok"
        reason = None
    else:
        result_status = "empty"
        reason = "no_rows"

    result = {
        "status": result_status,
        "reason": reason,
        "status_code": status,
        "listing_url": urljoin(EAUCTION_BASE, EAUCTION_LISTING_PATH),
        "final_url": final_url,
        "blocked": result_status == "blocked",
        "blockers": blockers,
        "row_count": len(rows),
        "rows": rows[:20],
        "html_length": len(html),
        "tabs_available": tabs,
        "pagination_links": len(pagination),
        "detail_accessible": detail_accessible,
        "detail_status_code": detail_status,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    work_html = Path("work/eauction/latest_listing.html")
    work_html.parent.mkdir(parents=True, exist_ok=True)
    work_html.write_text(html[:800_000], encoding="utf-8")

    fixture_path = out_path.parent / "listing_fixture.html"
    fixture_path.write_text(html[:800_000], encoding="utf-8")

    logger.info(
        "Probe: status=%s rows=%d blockers=%s detail=%s pagination=%d",
        result_status,
        len(rows),
        blockers,
        detail_accessible,
        len(pagination),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Probe eauction.gov.in public listing page")
    parser.add_argument("--out", type=Path, default=Path("work/eauction_probe.json"))
    parser.add_argument("--fetch-detail", action="store_true")
    parser.add_argument(
        "--tab",
        choices=("closingTodayTab", "closingWeekTab", "closingTwoWeekTab"),
        default=None,
    )
    args = parser.parse_args(argv)

    try:
        result = run_probe(out_path=args.out, fetch_detail=args.fetch_detail, tab=args.tab)
        if result["status"] == "blocked":
            logger.warning("eAuction probe blocked: %s", result.get("reason"))
            return 2
        if result["row_count"] == 0:
            logger.warning("eAuction probe returned no rows")
            return 2
        return 0
    except Exception as exc:
        logger.exception("Probe failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
