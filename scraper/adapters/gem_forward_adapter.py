from __future__ import annotations

from scraper.category_map import normalize_gem_category
from scraper.gem_forward_parser import GemForwardAuction, GemForwardItem
from scraper.models import AuctionRecord, ExtractionStatus, LotRecord


def _location_parts(auction: GemForwardAuction) -> str | None:
    parts = [auction.city, auction.district, auction.state, auction.pincode]
    cleaned = [p for p in parts if p]
    return ", ".join(cleaned) if cleaned else None


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(str(text).split()).strip()
    return cleaned or None


def _notice_body(auction: GemForwardAuction) -> str | None:
    """Prefer auction_detail; fall back to brief. Used as visible/searchable body."""
    detail = _clean(auction.auction_detail)
    brief = _clean(auction.auction_brief)
    if detail and brief and brief.lower() not in detail.lower():
        return f"{brief} {detail}".strip()
    return detail or brief


def _item_summary(auction: GemForwardAuction, lots: list[LotRecord]) -> str | None:
    """Keep rich notice prose — do not replace with a short lot title."""
    body = _notice_body(auction)
    if body:
        return body
    title = _clean(auction.title)
    if title:
        return title
    if lots and lots[0].item_title:
        return _clean(lots[0].item_title)
    return None


def _item_to_lot(
    item: GemForwardItem,
    index: int,
    *,
    notice: str | None,
    single_lot: bool,
) -> LotRecord:
    title = _clean(item.item_name) or f"Lot {index + 1}"
    # Put notice prose on the sole lot (or every lot when only one item).
    description = notice if single_lot else None
    return LotRecord(
        lot_id=str(item.sr_no or index + 1),
        item_title=title,
        item_description=description,
        lot_description_text=description,
        start_price_inr=item.opening_price_inr,
        start_price=item.opening_price_inr,
        price_parse_status="numeric" if item.opening_price_inr is not None else "missing",
        bid_increment=item.increment_price_inr,
    )


def adapt_gem_forward_auction(auction: GemForwardAuction) -> AuctionRecord:
    notice = _notice_body(auction)
    raw_items = list(auction.items)
    single_lot = len(raw_items) <= 1
    lots = [
        _item_to_lot(item, i, notice=notice, single_lot=single_lot)
        for i, item in enumerate(raw_items)
    ]
    if not lots and auction.title:
        lots = [
            LotRecord(
                lot_id="1",
                item_title=_clean(auction.title) or auction.title,
                item_description=notice,
                lot_description_text=notice,
                start_price_inr=auction.min_opening_price_inr,
                start_price=auction.min_opening_price_inr,
                price_parse_status=(
                    "numeric" if auction.min_opening_price_inr is not None else "missing"
                ),
            )
        ]
    elif lots and notice and not any(lot.lot_description_text for lot in lots):
        # Multi-lot: keep auction-level notice on lot 1 so UI/search still see body text.
        lots[0] = lots[0].model_copy(
            update={
                "item_description": notice,
                "lot_description_text": notice,
            }
        )

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

    item_summary = _item_summary(auction, lots)

    warnings: list[str] = []
    if auction.emd_amount_inr is None and auction.emd_required is not False:
        warnings.append("GeM: verify EMD and rules on the official GeM listing")

    search_parts = [
        auction.title,
        auction.auction_brief,
        auction.auction_detail,
        auction.category,
        auction.sub_category,
        seller,
        _location_parts(auction),
        *(lot.item_title for lot in lots if lot.item_title),
    ]

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
        search_text=" ".join(filter(None, (_clean(p) for p in search_parts))),
        parse_confidence="medium" if lots else "low",
        status=ExtractionStatus.COMPLETE if lots else ExtractionStatus.PARTIAL,
        total_lots=len(lots),
        warnings=warnings,
    )
