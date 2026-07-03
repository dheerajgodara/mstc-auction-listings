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
    GEM_FORWARD_PER_PAGE,
    GEM_FORWARD_REQUEST_DELAY_SEC,
)
from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError
from scraper.gem_forward_parser import (
    GemForwardAuction,
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


class GemForwardExport(BaseModel):
    generated_at: datetime
    source: str = "gem_forward"
    count: int
    auctions: list[GemForwardAuction]
    stats: dict = Field(default_factory=dict)


def scrape_gem_forward(
    *,
    client: GemForwardClient | None = None,
    max_pages: int | None = None,
    per_page: int = GEM_FORWARD_PER_PAGE,
    limit: int | None = None,
    enrich: bool = True,
    delay_sec: float = GEM_FORWARD_REQUEST_DELAY_SEC,
) -> list[GemForwardAuction]:
    cli = client or GemForwardClient(transport="auto")
    cli.init_session()

    first_html = cli.search_auctions_html(page=1, per_page=per_page)
    total_records = parse_listing_record_count(first_html)
    total_pages = max(1, ceil(total_records / per_page)) if total_records else 1
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    logger.info("GeM Forward: %d live auctions across %d page(s)", total_records, total_pages)

    all_listings = []
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

    auctions: list[GemForwardAuction] = []
    for i, listing in enumerate(all_listings):
        if not enrich:
            auctions.append(
                GemForwardAuction(
                    **listing.model_dump(),
                    auction_brief=listing.title,
                    detail_url=f"https://forwardauction.gem.gov.in{listing.notice_path}",
                    document_url=(
                        f"https://forwardauction.gem.gov.in{listing.document_path}"
                        if listing.document_path
                        else None
                    ),
                )
            )
            continue

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
            auctions.append(merge_auction(listing, detail, items))
        except Exception as exc:
            logger.warning("Failed to enrich auction %s: %s", listing.auction_id, exc)
            auctions.append(
                GemForwardAuction(
                    **listing.model_dump(),
                    auction_brief=listing.title,
                    detail_url=f"https://forwardauction.gem.gov.in{listing.notice_path}",
                )
            )

        if (i + 1) % 10 == 0:
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
    except Exception as exc:
        logger.exception("Scrape failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
