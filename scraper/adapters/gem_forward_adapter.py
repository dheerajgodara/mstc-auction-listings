from __future__ import annotations

from scraper.category_map import normalize_gem_category
from scraper.gem_forward_parser import GemForwardAuction, GemForwardItem
from scraper.models import AuctionRecord, ExtractionStatus, LotRecord


def _location_parts(auction: GemForwardAuction) -> str | None:
    parts = [auction.city, auction.district, auction.state, auction.pincode]
    cleaned = [p for p in parts if p]
    return ", ".join(cleaned) if cleaned else None


def _item_to_lot(item: GemForwardItem, index: int) -> LotRecord:
    return LotRecord(
        lot_id=str(item.sr_no or index + 1),
        item_title=item.item_name,
        start_price_inr=item.opening_price_inr,
        start_price=item.opening_price_inr,
        price_parse_status="numeric" if item.opening_price_inr is not None else "missing",
        bid_increment=item.increment_price_inr,
    )


def adapt_gem_forward_auction(auction: GemForwardAuction) -> AuctionRecord:
    lots = [_item_to_lot(item, i) for i, item in enumerate(auction.items)]
    if not lots and auction.title:
        lots = [
            LotRecord(
                lot_id="1",
                item_title=auction.title,
                start_price_inr=auction.min_opening_price_inr,
                start_price=auction.min_opening_price_inr,
                price_parse_status=(
                    "numeric" if auction.min_opening_price_inr is not None else "missing"
                ),
            )
        ]

    document_urls: list[str] = []
    for url in (auction.document_url, auction.rules_url):
        if url and url not in document_urls:
            document_urls.append(url)

    seller = auction.seller_name
    if not seller and auction.organisation:
        seller = ", ".join(auction.organisation)

    asset_category = normalize_gem_category(
        category=auction.category,
        sub_category=auction.sub_category,
        title=auction.title,
    )

    prices = [lot.start_price_inr for lot in lots if lot.start_price_inr is not None]
    min_price = min(prices) if prices else auction.min_opening_price_inr
    max_price = max(prices) if prices else auction.min_opening_price_inr

    item_summary = auction.auction_brief or auction.title
    if lots and len(lots) == 1 and lots[0].item_title:
        short = lots[0].item_title.strip()
        if short and len(short) <= 80:
            item_summary = short

    warnings: list[str] | None = None
    if auction.emd_amount_inr is None and auction.emd_required is not False:
        warnings = ["GeM: verify EMD and rules on the official GeM listing"]

    return AuctionRecord(
        id=f"gem_forward:{auction.auction_id}",
        source="gem_forward",
        source_auction_id=auction.auction_id,
        auction_number=auction.auction_id,
        region=auction.state or "GeM",
        office="GeM Forward",
        state=auction.state,
        asset_category=asset_category,
        platform="GeM Forward",
        seller=seller,
        location=_location_parts(auction),
        opening=auction.opening,
        closing=auction.closing,
        pre_bid_emd_amount=auction.emd_amount_inr,
        pre_bid_emd_required=auction.emd_required,
        emd_parse_status=(
            "auction_wise"
            if auction.emd_amount_inr is not None
            else ("not_required" if auction.emd_required is False else "unknown")
        ),
        detail_url=auction.detail_url,
        document_urls=document_urls,
        lots=lots,
        item_summary=item_summary,
        min_start_price=min_price,
        max_start_price=max_price,
        price_parse_status="numeric" if min_price is not None else "missing",
        search_text=" ".join(
            filter(
                None,
                [
                    auction.title,
                    auction.auction_brief,
                    auction.category,
                    auction.sub_category,
                    seller,
                    _location_parts(auction),
                ],
            )
        ),
        parse_confidence="medium" if lots else "low",
        status=ExtractionStatus.COMPLETE if lots else ExtractionStatus.PARTIAL,
        total_lots=len(lots),
        warnings=warnings,
    )
