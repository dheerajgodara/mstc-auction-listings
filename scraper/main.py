from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_JSON_OUT,
    DEFAULT_PDF_DIR,
    DEFAULT_THUMBS_DIR,
    OFFICE_CODES,
    PDF_DETAIL_URL,
    REGION_TO_STATE,
)
from scraper.document_cache import attach_documents_to_lot, process_auction_documents
from scraper.html_parser import fetch_and_parse_html_detail
from scraper.merger import merge_auction_record
from scraper.mstc_api import (
    fetch_all_listing_api,
    fetch_office_auctions,
    lot_types_from_flags,
    parse_mstc_datetime,
)
from scraper.models import AuctionRecord, AuctionsExport, ExtractionStatus, ListingApiAuction, ListingApiOfficeResponse
from scraper.pdf_downloader import download_pdf
from scraper.pdf_parser import parse_pdf_header, parse_pdf_lots
from scraper.export_guard import write_auctions_json
from scraper.retention import should_keep_auction

IST = ZoneInfo("Asia/Kolkata")
REQUEST_DELAY_SEC = 0.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scraper.main")


def listing_to_base(
    auction: ListingApiAuction,
    office: ListingApiOfficeResponse,
) -> AuctionRecord:
    opening = parse_mstc_datetime(auction.opening)
    closing = parse_mstc_datetime(auction.Closing)
    region = auction.region or office.REGION
    return AuctionRecord(
        id=auction.id,
        auction_number=auction.text,
        source="mstc",
        source_auction_id=auction.id,
        platform="MSTC",
        region=region,
        office=office.OFFICE,
        state=REGION_TO_STATE.get(region),
        opening=opening,
        closing=closing,
        lot_types=lot_types_from_flags(
            auction.GeneralLots,
            auction.RVSFLots,
            auction.HazardousWaste,
        ),
        mstc_html_url=f"https://www.mstcindia.co.in/TenderEntry/Lot_Item_Details_AucID.aspx?ARID={auction.id}",
        detail_url=f"https://www.mstcindia.co.in/TenderEntry/Lot_Item_Details_AucID.aspx?ARID={auction.id}",
        source_pdf_url=PDF_DETAIL_URL,
        status=ExtractionStatus.LISTING_ONLY,
    )


def _passes_min_closing(record: AuctionRecord, min_closing: datetime | None) -> bool:
    if min_closing is None or record.closing is None:
        return True
    return record.closing >= min_closing


def resolve_auction_listing(auction_id: str) -> tuple[AuctionRecord, ListingApiOfficeResponse | None]:
    for office_code in OFFICE_CODES:
        try:
            office_meta = fetch_office_auctions(office_code)
            for auction in office_meta.auction:
                if auction.id == auction_id:
                    return listing_to_base(auction, office_meta), office_meta
        except Exception as exc:
            logger.debug("Office %s lookup failed for %s: %s", office_code, auction_id, exc)
    stub = AuctionRecord(
        id=auction_id,
        auction_number=auction_id,
        region="",
        office="",
        mstc_html_url=f"https://www.mstcindia.co.in/TenderEntry/Lot_Item_Details_AucID.aspx?ARID={auction_id}",
        source_pdf_url=PDF_DETAIL_URL,
        status=ExtractionStatus.LISTING_ONLY,
    )
    return stub, None


def enrich_auction(
    base: AuctionRecord,
    *,
    pdf_dir: Path,
    skip_pdf: bool,
    stats: dict,
) -> AuctionRecord:
    html_data = None
    pdf_lots = None
    pdf_header = None
    pdf_url = None

    try:
        time.sleep(REQUEST_DELAY_SEC)
        html_data = fetch_and_parse_html_detail(base.id)
        if html_data.get("opening_raw"):
            dt = parse_mstc_datetime(html_data["opening_raw"])
            if dt:
                base.opening = dt
        if html_data.get("closing_raw"):
            dt = parse_mstc_datetime(html_data["closing_raw"])
            if dt:
                base.closing = dt
    except Exception as exc:
        logger.warning("HTML failed for %s: %s", base.id, exc)
        base.errors.append(f"html: {exc}")
        stats["html_failures"] = stats.get("html_failures", 0) + 1

    if not skip_pdf:
        try:
            time.sleep(REQUEST_DELAY_SEC)
            pdf_path = pdf_dir / f"{base.id}.pdf"
            if not pdf_path.exists():
                download_pdf(base.id, pdf_path)
                stats["pdf_downloaded"] = stats.get("pdf_downloaded", 0) + 1
            else:
                logger.debug("Using cached PDF %s", pdf_path)
                stats["pdf_cache_hits"] = stats.get("pdf_cache_hits", 0) + 1
            pdf_lots = parse_pdf_lots(pdf_path)
            pdf_header = parse_pdf_header(pdf_path)
            pdf_url = f"pdfs/{base.id}.pdf"
            stats["lots_parsed"] = stats.get("lots_parsed", 0) + len(pdf_lots or [])
        except Exception as exc:
            logger.warning("PDF failed for %s: %s", base.id, exc)
            base.errors.append(f"pdf: {exc}")
            stats["pdf_failures"] = stats.get("pdf_failures", 0) + 1
            stats.setdefault("pdf_failed_ids", []).append(base.id)

    record = merge_auction_record(
        base,
        html_data=html_data,
        pdf_lots=pdf_lots,
        pdf_header=pdf_header,
        pdf_relative_url=pdf_url,
        source_pdf_url=PDF_DETAIL_URL,
    )
    if record.errors:
        record.status = ExtractionStatus.PARTIAL if record.lots else ExtractionStatus.FAILED
    return record


def run_pipeline(
    *,
    out_path: Path,
    pdf_dir: Path,
    docs_dir: Path,
    thumbs_dir: Path,
    skip_pdf: bool = False,
    skip_docs: bool = False,
    max_docs_per_run: int = 100,
    limit: int | None = None,
    limit_per_office: int | None = None,
    office: str | None = None,
    auction_id: str | None = None,
    include_auction_ids: set[str] | None = None,
    min_closing_date: str | None = None,
    allow_small_output: bool = False,
) -> AuctionsExport:
    min_closing = None
    if min_closing_date:
        min_closing = datetime.strptime(min_closing_date, "%Y-%m-%d").replace(tzinfo=IST)

    all_offices: list[tuple[ListingApiOfficeResponse, list[ListingApiAuction]]] = []

    if auction_id:
        base, office_meta = resolve_auction_listing(auction_id)
        if office_meta:
            all_offices = [(office_meta, [next(a for a in office_meta.auction if a.id == auction_id)])]
        else:
            all_offices = [
                (
                    ListingApiOfficeResponse(OFFICE="", REGION="", auction=[]),
                    [
                        ListingApiAuction(
                            id=auction_id,
                            text=auction_id,
                            opening="",
                            Closing="",
                            GeneralLots="",
                            RVSFLots="",
                            HazardousWaste="",
                            OFF_NAME="",
                            region="",
                        )
                    ],
                )
            ]
    elif office:
        office = office.upper()
        if office not in OFFICE_CODES:
            raise ValueError(f"Unknown office {office!r}; valid: {', '.join(OFFICE_CODES)}")
        office_meta = fetch_office_auctions(office)
        all_offices = [(office_meta, office_meta.auction)]
    else:
        all_offices = fetch_all_listing_api()

    records: list[AuctionRecord] = []
    stats: dict = {
        "html_failures": 0,
        "pdf_failures": 0,
        "pdf_failed_ids": [],
        "pdf_downloaded": 0,
        "pdf_cache_hits": 0,
        "lots_parsed": 0,
        "extraction_errors": [],
        "per_office_counts": {},
        "listing_before_filter": 0,
        "excluded_retention": 0,
        "excluded_before_min_closing": 0,
        "excluded_missing_closing_listing": 0,
        "excluded_not_in_work_plan": 0,
        "offices_scanned": 0,
        "documents": {
            "refs_found": 0,
            "attempted": 0,
            "downloaded": 0,
            "cache_hits": 0,
            "thumbnails_ready": 0,
            "failed": 0,
            "skipped_due_limit": 0,
            "failed_by_reason": {},
            "failed_by_doc_type": {},
        },
    }

    docs_remaining = max_docs_per_run
    session = requests.Session()

    for office_meta, auctions in all_offices:
        office_code = office_meta.OFFICE if hasattr(office_meta, "OFFICE") else office_meta.REGION
        region_key = office_meta.REGION or office_code
        office_processed = 0
        stats["offices_scanned"] = stats.get("offices_scanned", 0) + 1

        for auction in auctions:
            if auction_id and auction.id != auction_id:
                continue
            if include_auction_ids is not None and auction.id not in include_auction_ids:
                stats["excluded_not_in_work_plan"] = stats.get("excluded_not_in_work_plan", 0) + 1
                continue
            stats["listing_before_filter"] = stats.get("listing_before_filter", 0) + 1
            if not auction_id and min_closing is None and not should_keep_auction(auction):
                stats["excluded_retention"] = stats.get("excluded_retention", 0) + 1
                continue
            base = (
                listing_to_base(auction, office_meta)
                if office_meta.OFFICE
                else resolve_auction_listing(auction.id)[0]
            )
            if not auction_id and min_closing is not None:
                if base.closing is None:
                    stats["excluded_missing_closing_listing"] = (
                        stats.get("excluded_missing_closing_listing", 0) + 1
                    )
                    continue
                if not _passes_min_closing(base, min_closing):
                    stats["excluded_before_min_closing"] = (
                        stats.get("excluded_before_min_closing", 0) + 1
                    )
                    continue
            elif not auction_id and not _passes_min_closing(base, min_closing):
                continue
            enriched = enrich_auction(base, pdf_dir=pdf_dir, skip_pdf=skip_pdf, stats=stats)
            if not auction_id and min_closing is not None and not _passes_min_closing(enriched, min_closing):
                if enriched.closing is None:
                    stats["excluded_missing_closing_listing"] = (
                        stats.get("excluded_missing_closing_listing", 0) + 1
                    )
                else:
                    stats["excluded_before_min_closing"] = (
                        stats.get("excluded_before_min_closing", 0) + 1
                    )
                continue
            if not skip_docs:
                enriched, docs_remaining = process_auction_documents(
                    enriched,
                    docs_dir=docs_dir,
                    thumbs_dir=thumbs_dir,
                    skip_docs=False,
                    max_docs_remaining=docs_remaining,
                    session=session,
                    stats=stats,
                )
            else:
                enriched = enriched.model_copy(
                    update={"lots": [attach_documents_to_lot(lot) for lot in enriched.lots]}
                )
            if enriched.errors:
                stats["extraction_errors"].append({"id": enriched.id, "errors": enriched.errors})
            records.append(enriched)
            office_processed += 1

            if limit_per_office and office_processed >= limit_per_office:
                break
            if limit and len(records) >= limit:
                break

        if office_processed:
            stats["per_office_counts"][region_key] = office_processed

        if limit and len(records) >= limit:
            break

    records.sort(key=lambda r: r.closing or datetime.min.replace(tzinfo=IST))

    all_missing: dict[str, int] = {}
    for r in records:
        for f in r.missing_fields:
            all_missing[f] = all_missing.get(f, 0) + 1
    stats["missing_field_counts"] = all_missing
    stats["auctions_parsed"] = len(records)
    stats["total_lots_in_export"] = sum(len(r.lots) for r in records)

    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(records),
        auctions=records,
        stats=stats,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_auctions_json(
        out_path,
        export.model_dump(mode="json"),
        allow_small_output=allow_small_output or bool(auction_id),
    )
    logger.info(
        "Wrote %d auctions (%d lots) to %s",
        export.count,
        stats["total_lots_in_export"],
        out_path,
    )
    return export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MSTC auction listing scraper")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--thumbs-dir", type=Path, default=DEFAULT_THUMBS_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Global max auctions to process")
    parser.add_argument(
        "--limit-per-office",
        type=int,
        default=None,
        help="Max retained auctions to process per office (stratified sampling)",
    )
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF download/parse")
    parser.add_argument("--skip-docs", action="store_true", help="Skip lot document download/cache")
    parser.add_argument(
        "--max-docs-per-run",
        type=int,
        default=100,
        help="Max lot documents to download/cache in one run (default 100)",
    )
    parser.add_argument("--office", type=str, default=None, help="Single office code e.g. JPR")
    parser.add_argument(
        "--auction-id",
        type=str,
        default=None,
        help="Process a single auction ID (e.g. 587164)",
    )
    parser.add_argument(
        "--min-closing-date",
        type=str,
        default=None,
        help="Only auctions closing on/after YYYY-MM-DD",
    )
    parser.add_argument(
        "--allow-small-output",
        action="store_true",
        help="Allow writing fewer than 100 auctions to protected production JSON paths",
    )
    args = parser.parse_args(argv)

    try:
        export = run_pipeline(
            out_path=args.out,
            pdf_dir=args.pdf_dir,
            docs_dir=args.docs_dir,
            thumbs_dir=args.thumbs_dir,
            skip_pdf=args.skip_pdf,
            skip_docs=args.skip_docs,
            max_docs_per_run=args.max_docs_per_run,
            limit=args.limit,
            limit_per_office=args.limit_per_office,
            office=args.office,
            auction_id=args.auction_id,
            min_closing_date=args.min_closing_date,
            allow_small_output=args.allow_small_output,
        )
        s = export.stats
        logger.info(
            "Summary: auctions=%d lots=%d html_fail=%d pdf_fail=%d",
            s.get("auctions_parsed", 0),
            s.get("total_lots_in_export", 0),
            s.get("html_failures", 0),
            s.get("pdf_failures", 0),
        )
        if s.get("documents"):
            logger.info("Documents: %s", s["documents"])
        if s.get("missing_field_counts"):
            logger.info("Missing fields: %s", s["missing_field_counts"])
        return 0
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
