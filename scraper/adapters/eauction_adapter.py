from __future__ import annotations

from typing import Any

from scraper.category_map import normalize_eauction_category
from scraper.models import AuctionRecord, ExtractionStatus, LotRecord


def _format_organisation(org: str | None) -> str | None:
    if not org:
        return None
    parts = [p.strip() for p in org.split("||") if p.strip()]
    if not parts:
        return org.strip() or None
    if len(parts) == 1:
        return parts[0]
    return parts[-1]


def _item_summary(title: str, product_category: str | None) -> str:
    if product_category and product_category.lower() not in title.lower():
        return f"{title} ({product_category})"
    return title


def adapt_eauction_record(raw: dict[str, Any]) -> AuctionRecord:
    auction_id = str(raw.get("auction_id") or raw.get("id") or "")
    title = raw.get("title") or f"Auction {auction_id}"
    start_price = raw.get("starting_price_inr")
    emd = raw.get("emd_inr")
    organisation = _format_organisation(raw.get("organisation"))
    product_category = raw.get("product_category")

    asset_category = normalize_eauction_category(
        product_category=product_category,
        sub_category=raw.get("sub_category"),
        title=title,
    )

    document_urls = list(raw.get("document_urls") or [])
    detail_url = raw.get("detail_url")

    lot = LotRecord(
        lot_id="1",
        item_title=title,
        item_description=raw.get("sub_category") or product_category,
        start_price_inr=start_price,
        start_price=start_price,
        price_parse_status="numeric" if start_price is not None else "missing",
        pre_bid_emd_amount=emd,
        location=raw.get("location"),
        category=product_category,
        product_type=raw.get("sub_category"),
        bid_increment=raw.get("increment_inr"),
    )

    has_detail = bool(organisation or product_category or document_urls)
    confidence = "medium" if has_detail else "low"

    return AuctionRecord(
        id=f"eauction:{auction_id}",
        source="eauction",
        source_auction_id=auction_id,
        auction_number=auction_id,
        region=raw.get("state") or "eAuction",
        office=organisation or "eAuction.gov.in",
        state=raw.get("state"),
        asset_category=asset_category,
        platform="eAuction.gov.in",
        seller=organisation,
        location=raw.get("location"),
        opening=raw.get("publish_date"),
        closing=raw.get("closing_date"),
        pre_bid_emd_amount=emd,
        emd_parse_status="auction_wise" if emd is not None else "unknown",
        detail_url=detail_url,
        document_urls=document_urls,
        lots=[lot],
        item_summary=_item_summary(title, product_category),
        min_start_price=start_price,
        max_start_price=start_price,
        price_parse_status=lot.price_parse_status,
        search_text=" ".join(
            filter(
                None,
                [
                    title,
                    organisation,
                    product_category,
                    raw.get("sub_category"),
                    raw.get("location"),
                    raw.get("state"),
                ],
            )
        ),
        parse_confidence=confidence,
        status=ExtractionStatus.COMPLETE if has_detail else ExtractionStatus.PARTIAL,
        total_lots=1,
    )
