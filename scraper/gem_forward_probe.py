from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scraper.gem_forward_probe")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe GeM Forward Auction connectivity and listing extractability")
    parser.add_argument(
        "--transport",
        choices=("auto", "direct", "ssh"),
        default="auto",
        help="HTTP transport: auto tries direct then SSH via Hostinger",
    )
    parser.add_argument("--page", type=int, default=1, help="Listing page to fetch")
    parser.add_argument("--per-page", type=int, default=3, help="Auctions per listing page")
    parser.add_argument("--dump-dir", type=Path, default=None, help="Optional directory to save raw HTML")
    parser.add_argument("--enrich", type=int, default=1, help="Fetch detail+rules for first N listings (0=skip)")
    args = parser.parse_args(argv)

    client = GemForwardClient(transport=args.transport)
    try:
        probe = client.probe_connectivity()
        logger.info("Connectivity OK via %s", probe["transport"])

        listing_html = client.search_auctions_html(page=args.page, per_page=args.per_page)
        from scraper.gem_forward_parser import (
            parse_detail_page,
            parse_listing_page,
            parse_listing_record_count,
            parse_rules_page,
            merge_auction,
        )

        record_count = parse_listing_record_count(listing_html)
        listings = parse_listing_page(listing_html)
        logger.info("Listing page %d: %d records on server, %d parsed", args.page, record_count, len(listings))

        if args.dump_dir:
            args.dump_dir.mkdir(parents=True, exist_ok=True)
            (args.dump_dir / f"listing_page{args.page}.html").write_text(listing_html, encoding="utf-8")

        samples = []
        for listing in listings[: max(args.enrich, 0)]:
            detail_html = client.get_html(listing.notice_path)
            detail = parse_detail_page(detail_html)
            items: list = []
            rules_path = detail.get("rules_path")
            if rules_path:
                rules_html = client.get_html(rules_path)
                items = parse_rules_page(rules_html)
                if args.dump_dir:
                    (args.dump_dir / f"detail_{listing.auction_id}.html").write_text(detail_html, encoding="utf-8")
                    (args.dump_dir / f"rules_{listing.auction_id}.html").write_text(rules_html, encoding="utf-8")
            auction = merge_auction(listing, detail, items)
            samples.append(auction.model_dump(mode="json"))

        result = {
            "probe": probe,
            "record_count": record_count,
            "parsed_listings": len(listings),
            "sample_listings": [l.model_dump(mode="json") for l in listings[:5]],
            "enriched_samples": samples,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except GemForwardTransportError as exc:
        logger.error("%s", exc)
        return 2
    except Exception as exc:
        logger.exception("Probe failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
