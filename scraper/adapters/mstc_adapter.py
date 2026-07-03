from __future__ import annotations

from scraper.category_map import normalize_mstc_category
from scraper.models import AuctionRecord, LotRecord


def prefix_source_id(source: str, raw_id: str) -> str:
    return f"{source}:{raw_id}"


def adapt_mstc_record(record: AuctionRecord) -> AuctionRecord:
    """Ensure MSTC records carry unified multi-source fields without changing live IDs."""
    lots = list(record.lots)
    primary_lot: LotRecord | None = lots[0] if lots else None
    asset_category = normalize_mstc_category(
        category=primary_lot.category if primary_lot else None,
        product_type=primary_lot.product_type if primary_lot else None,
        lot_title=primary_lot.item_title if primary_lot else record.item_summary,
        lot_description=primary_lot.item_description if primary_lot else None,
    )
    document_urls = list(record.document_urls)
    if record.pdf_url and record.pdf_url not in document_urls:
        document_urls.insert(0, record.pdf_url)

    return record.model_copy(
        update={
            "source": "mstc",
            "source_auction_id": record.source_auction_id or record.id,
            "platform": record.platform or "MSTC",
            "detail_url": record.detail_url or record.mstc_html_url,
            "document_urls": document_urls,
            "asset_category": record.asset_category or asset_category,
        }
    )
