from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from math import ceil
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from scraper.config import (
    DEFAULT_GEM_FORWARD_JSON_OUT,
    GEM_FORWARD_LIVE_MIN_COUNT,
    GEM_FORWARD_PER_PAGE,
    GEM_FORWARD_REQUEST_DELAY_SEC,
    GEM_FORWARD_STATUS_LIVE,
)
from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError
from scraper.gem_forward_parser import (
    GemForwardAuction,
    GemForwardListing,
    merge_auction,
    parse_detail_page,
    parse_listing_page,
    parse_listing_record_count,
    parse_rules_page,
)

IST = ZoneInfo("Asia/Kolkata")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scraper.gem_forward_scraper")


class GemForwardCoverageError(RuntimeError):
    """Live GeM listing count is too low — wrong xStatus or broken search."""


class GemForwardExport(BaseModel):
    generated_at: datetime
    source: str = "gem_forward"
    count: int
    auctions: list[GemForwardAuction]
    stats: dict = Field(default_factory=dict)


def assert_live_coverage(total_records: int, *, min_count: int = GEM_FORWARD_LIVE_MIN_COUNT) -> None:
    """Fail loud if Live search looks like the old xStatus=2 subset (~100–150)."""
    if total_records < min_count:
        raise GemForwardCoverageError(
            f"GeM Forward Live returned only {total_records} auctions "
            f"(min expected {min_count}). Homepage Live uses xStatus="
            f"{GEM_FORWARD_STATUS_LIVE}; a low count usually means the wrong "
            f"status filter (historical bug: xStatus=2 returned ~118 of ~500)."
        )


def _listing_by_keyword(cli: GemForwardClient, auction_id: str, *, per_page: int) -> GemForwardListing | None:
    """Resolve a single auction via keyword search (works across Live tabs)."""
    html = cli.search_auctions_html(
        page=1,
        per_page=per_page,
        status=GEM_FORWARD_STATUS_LIVE,
        keyword=str(auction_id),
    )
    for listing in parse_listing_page(html):
        if listing.auction_id == str(auction_id):
            return listing
    return None


def _enrich_listing(
    cli: GemForwardClient,
    listing: GemForwardListing,
    *,
    enrich: bool,
    delay_sec: float,
) -> GemForwardAuction:
    if not enrich:
        return GemForwardAuction(
            **listing.model_dump(),
            auction_brief=listing.title,
            detail_url=f"https://forwardauction.gem.gov.in{listing.notice_path}",
            document_url=(
                f"https://forwardauction.gem.gov.in{listing.document_path}"
                if listing.document_path
                else None
            ),
        )
    try:
        time.sleep(delay_sec)
        detail_html = cli.get_html(listing.notice_path)
        detail = parse_detail_page(detail_html)
        items = []
        rules_path = detail.get("rules_path")
        if rules_path:
            time.sleep(delay_sec)
            rules_html = cli.get_html(rules_path)
            items = parse_rules_page(rules_html)
        return merge_auction(listing, detail, items)
    except Exception as exc:
        logger.warning("Failed to enrich auction %s: %s", listing.auction_id, exc)
        return GemForwardAuction(
            **listing.model_dump(),
            auction_brief=listing.title,
            detail_url=f"https://forwardauction.gem.gov.in{listing.notice_path}",
            document_url=(
                f"https://forwardauction.gem.gov.in{listing.document_path}"
                if listing.document_path
                else None
            ),
        )


def scrape_gem_forward(
    *,
    client: GemForwardClient | None = None,
    max_pages: int | None = None,
    per_page: int = GEM_FORWARD_PER_PAGE,
    limit: int | None = None,
    enrich: bool = True,
    delay_sec: float = GEM_FORWARD_REQUEST_DELAY_SEC,
    include_auction_ids: set[str] | None = None,
    skip_coverage_check: bool = False,
) -> list[GemForwardAuction]:
    cli = client or GemForwardClient(transport="auto")
    cli.init_session()

    # Targeted enrich: prefer keyword lookup so IDs not on the first N Live pages
    # (or briefly missing from pagination) still resolve.
    if include_auction_ids is not None and enrich:
        wanted = {str(a) for a in include_auction_ids}
        found: dict[str, GemForwardListing] = {}
        # Still pull Live pages once so we catch bulk cheaply, then keyword-fill gaps.
        first_html = cli.search_auctions_html(page=1, per_page=per_page)
        total_records = parse_listing_record_count(first_html)
        if not skip_coverage_check:
            assert_live_coverage(total_records)
        total_pages = max(1, ceil(total_records / per_page)) if total_records else 1
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)
        logger.info(
            "GeM Forward targeted enrich: %d ids, Live catalog=%d (%d pages)",
            len(wanted),
            total_records,
            total_pages,
        )
        for page in range(1, total_pages + 1):
            html = first_html if page == 1 else cli.search_auctions_html(page=page, per_page=per_page)
            for listing in parse_listing_page(html):
                if listing.auction_id in wanted and listing.auction_id not in found:
                    found[listing.auction_id] = listing
            if len(found) >= len(wanted):
                break
            if page < total_pages:
                time.sleep(delay_sec)

        missing = sorted(wanted - set(found))
        if missing:
            logger.info("GeM keyword fallback for %d missing id(s)", len(missing))
            for aid in missing:
                time.sleep(delay_sec)
                listing = _listing_by_keyword(cli, aid, per_page=per_page)
                if listing:
                    found[aid] = listing
                else:
                    logger.warning("GeM auction %s not found via Live list or keyword search", aid)

        auctions: list[GemForwardAuction] = []
        for i, aid in enumerate(sorted(found)):
            auctions.append(_enrich_listing(cli, found[aid], enrich=True, delay_sec=delay_sec))
            if (i + 1) % 10 == 0:
                logger.info("Enriched %d/%d targeted auctions", i + 1, len(found))
        return auctions

    first_html = cli.search_auctions_html(page=1, per_page=per_page)
    total_records = parse_listing_record_count(first_html)
    if not skip_coverage_check and include_auction_ids is None:
        assert_live_coverage(total_records)
    total_pages = max(1, ceil(total_records / per_page)) if total_records else 1
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    logger.info(
        "GeM Forward: %d live auctions across %d page(s) (xStatus=%s)",
        total_records,
        total_pages,
        GEM_FORWARD_STATUS_LIVE,
    )

    all_listings: list[GemForwardListing] = []
    for page in range(1, total_pages + 1):
        html = first_html if page == 1 else cli.search_auctions_html(page=page, per_page=per_page)
        listings = parse_listing_page(html)
        all_listings.extend(listings)
        logger.info("Page %d/%d: parsed %d listings", page, total_pages, len(listings))
        if limit and len(all_listings) >= limit:
            all_listings = all_listings[:limit]
            break
        if page < total_pages:
            time.sleep(delay_sec)

    if include_auction_ids is not None:
        wanted = {str(a) for a in include_auction_ids}
        all_listings = [listing for listing in all_listings if listing.auction_id in wanted]

    auctions = []
    for i, listing in enumerate(all_listings):
        auctions.append(_enrich_listing(cli, listing, enrich=enrich, delay_sec=delay_sec))
        if enrich and (i + 1) % 10 == 0:
            logger.info("Enriched %d/%d auctions", i + 1, len(all_listings))

    return auctions


def run_export(
    *,
    out_path: Path,
    max_pages: int | None = None,
    limit: int | None = None,
    listing_only: bool = False,
    transport: str = "auto",
) -> GemForwardExport:
    client = GemForwardClient(transport=transport)
    auctions = scrape_gem_forward(
        client=client,
        max_pages=max_pages,
        limit=limit,
        enrich=not listing_only,
    )

    with_prices = sum(1 for a in auctions if a.min_opening_price_inr is not None)
    export = GemForwardExport(
        generated_at=datetime.now(IST),
        count=len(auctions),
        auctions=auctions,
        stats={
            "transport": client._active_transport,
            "with_opening_price": with_prices,
            "listing_only": listing_only,
            "x_status": GEM_FORWARD_STATUS_LIVE,
        },
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(export.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote %d GeM Forward auctions to %s", export.count, out_path)
    return export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape GeM Forward Auction listings")
    parser.add_argument("--out", type=Path, default=DEFAULT_GEM_FORWARD_JSON_OUT)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--listing-only", action="store_true", help="Skip detail/rules enrichment")
    parser.add_argument("--transport", choices=("auto", "direct", "ssh"), default="auto")
    args = parser.parse_args(argv)

    try:
        export = run_export(
            out_path=args.out,
            max_pages=args.max_pages,
            limit=args.limit,
            listing_only=args.listing_only,
            transport=args.transport,
        )
        logger.info(
            "Done: auctions=%d with_prices=%d transport=%s",
            export.count,
            export.stats.get("with_opening_price", 0),
            export.stats.get("transport"),
        )
        return 0
    except GemForwardTransportError as exc:
        logger.error("%s", exc)
        return 2
    except GemForwardCoverageError as exc:
        logger.error("%s", exc)
        return 3
    except Exception as exc:
        logger.exception("Scrape failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
