from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.adapters.eauction_adapter import adapt_eauction_record
from scraper.adapters.gem_forward_adapter import adapt_gem_forward_auction
from scraper.adapters.mstc_adapter import adapt_mstc_record
from scraper.batch_manifest import (
    BATCH_STATUS_DONE,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_SKIPPED,
    BatchManifest,
)
from scraper.category_map import should_exclude_category
from scraper.config import DEFAULT_DOCS_DIR, DEFAULT_PDF_DIR, DEFAULT_THUMBS_DIR, OFFICE_CODES
from scraper.eauction_scraper import scrape_eauction_tabs
from scraper.export_guard import write_auctions_json
from scraper.filters import apply_future_filter, parse_min_closing_date
from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError
from scraper.gem_forward_scraper import scrape_gem_forward
from scraper.incremental_plan import ids_by_source_for_action, load_work_plan, mstc_ids_by_office_for_action
from scraper.main import run_pipeline
from scraper.models import AuctionRecord, AuctionsExport

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.batch_run")

EAUCTION_TABS = ("closingTodayTab", "closingWeekTab", "closingTwoWeekTab")
GEM_BATCH_ID = "gem_forward_latest"
EAUCTION_BATCH_ID = "eauction_latest"


def _write_batch_export(path: Path, export: AuctionsExport) -> None:
    payload = export.model_dump(mode="json")
    write_auctions_json(path, payload)


def _batch_done(manifest: BatchManifest, batch_id: str, batch_dir: Path, *, force: bool) -> bool:
    if force:
        return False
    batch = manifest.get_batch(batch_id)
    if not batch or batch.get("status") != BATCH_STATUS_DONE:
        return False
    output_file = batch.get("output_file")
    return bool(output_file and (batch_dir / output_file).is_file())


def run_mstc_office_batch(
    *,
    office: str,
    batch_dir: Path,
    manifest: BatchManifest,
    pdf_dir: Path,
    docs_dir: Path,
    thumbs_dir: Path,
    min_closing_date: str,
    max_docs_per_run: int,
    force: bool,
    skip_docs: bool = False,
    include_auction_ids: set[str] | None = None,
) -> int:
    batch_id = f"mstc_{office}"
    output_file = f"mstc_{office}.json"
    out_path = batch_dir / output_file

    if _batch_done(manifest, batch_id, batch_dir, force=force):
        logger.info("Skipping completed MSTC batch %s", batch_id)
        manifest.upsert_batch({**manifest.get_batch(batch_id), "batch_id": batch_id, "status": BATCH_STATUS_SKIPPED})
        return 0

    manifest.mark_running(
        batch_id,
        source="mstc",
        office=office,
        output_file=output_file,
    )
    try:
        export = run_pipeline(
            out_path=out_path,
            pdf_dir=pdf_dir,
            docs_dir=docs_dir,
            thumbs_dir=thumbs_dir,
            office=office,
            min_closing_date=min_closing_date,
            max_docs_per_run=max_docs_per_run,
            skip_docs=skip_docs,
            include_auction_ids=include_auction_ids,
        )
        records = [adapt_mstc_record(r) for r in export.auctions]
        min_closing = parse_min_closing_date(min_closing_date)
        records, filter_stats = apply_future_filter(records, min_closing)
        final = AuctionsExport(
            generated_at=datetime.now(IST),
            count=len(records),
            auctions=records,
            stats={**export.stats, "future_filter": filter_stats, "office": office},
        )
        _write_batch_export(out_path, final)

        docs = export.stats.get("documents", {})
        manifest.mark_done(
            batch_id,
            source="mstc",
            office=office,
            output_file=output_file,
            auction_count=final.count,
            lot_count=sum(len(r.lots) for r in records),
            pdf_downloaded=export.stats.get("pdf_downloaded", 0),
            pdf_cache_hits=export.stats.get("pdf_cache_hits", 0),
            html_failures=export.stats.get("html_failures", 0),
            pdf_failures=export.stats.get("pdf_failures", 0),
            documents=docs,
            future_filter=filter_stats,
            deep_parse_filter_enabled=include_auction_ids is not None,
            deep_parse_ids_requested=len(include_auction_ids) if include_auction_ids is not None else None,
        )
        logger.info("MSTC office %s done: %d auctions", office, final.count)
        return final.count
    except Exception as exc:
        logger.exception("MSTC office %s failed: %s", office, exc)
        manifest.mark_failed(batch_id, str(exc), source="mstc", office=office, output_file=output_file)
        return 0


def run_gem_batch(
    *,
    batch_dir: Path,
    manifest: BatchManifest,
    min_closing_date: str,
    force: bool,
    include_auction_ids: set[str] | None = None,
) -> int:
    batch_id = GEM_BATCH_ID
    output_file = "gem_forward_latest.json"
    out_path = batch_dir / output_file

    if _batch_done(manifest, batch_id, batch_dir, force=force):
        logger.info("Skipping completed GeM batch")
        manifest.upsert_batch({**manifest.get_batch(batch_id), "batch_id": batch_id, "status": BATCH_STATUS_SKIPPED})
        return 0

    if include_auction_ids is not None and not include_auction_ids:
        export = AuctionsExport(
            generated_at=datetime.now(IST),
            count=0,
            auctions=[],
            stats={"deep_parse_filter_enabled": True, "deep_parse_ids_requested": 0},
        )
        _write_batch_export(out_path, export)
        manifest.mark_done(batch_id, source="gem_forward", output_file=output_file, auction_count=0, lot_count=0)
        logger.info("GeM Forward skipped: no deep-parse IDs")
        return 0

    manifest.mark_running(batch_id, source="gem_forward", output_file=output_file)
    warnings: list[str] = []
    transport_used = "unknown"
    try:
        client = GemForwardClient(transport="auto")
        auctions = scrape_gem_forward(client=client, enrich=True, include_auction_ids=include_auction_ids)
        transport_used = client._active_transport
    except GemForwardTransportError as exc:
        warnings.append(f"auto transport failed: {exc}")
        logger.warning("GeM auto transport failed, trying direct: %s", exc)
        try:
            client = GemForwardClient(transport="direct")
            auctions = scrape_gem_forward(client=client, enrich=True, include_auction_ids=include_auction_ids)
            transport_used = "direct"
        except Exception as direct_exc:
            manifest.mark_failed(batch_id, str(direct_exc), source="gem_forward", output_file=output_file)
            return 0

    min_closing = parse_min_closing_date(min_closing_date)
    records: list[AuctionRecord] = []
    enrich_fail = 0
    for auction in auctions:
        try:
            record = adapt_gem_forward_auction(auction)
            if should_exclude_category(record.asset_category, source="gem_forward"):
                continue
            records.append(record)
        except Exception as exc:
            enrich_fail += 1
            warnings.append(f"adapt failed {auction.auction_id}: {exc}")

    before = len(records)
    records, filter_stats = apply_future_filter(records, min_closing)
    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(records),
        auctions=records,
        stats={
            "found_before_filter": before,
            "transport": transport_used,
            "enrich_fail": enrich_fail,
            "warnings": warnings,
            "future_filter": filter_stats,
            "with_price": sum(1 for r in records if r.min_start_price is not None),
            "with_document_urls": sum(1 for r in records if r.document_urls),
            "deep_parse_filter_enabled": include_auction_ids is not None,
            "deep_parse_ids_requested": len(include_auction_ids) if include_auction_ids is not None else None,
        },
    )
    _write_batch_export(out_path, export)
    manifest.mark_done(
        batch_id,
        source="gem_forward",
        output_file=output_file,
        auction_count=export.count,
        lot_count=sum(len(r.lots) for r in records),
        transport=transport_used,
        warnings=warnings,
        future_filter=filter_stats,
    )
    logger.info("GeM Forward done: %d auctions", export.count)
    return export.count


def run_eauction_batch(
    *,
    batch_dir: Path,
    manifest: BatchManifest,
    min_closing_date: str,
    force: bool,
    include_auction_ids: set[str] | None = None,
) -> int:
    batch_id = EAUCTION_BATCH_ID
    output_file = "eauction_latest.json"
    out_path = batch_dir / output_file

    if _batch_done(manifest, batch_id, batch_dir, force=force):
        logger.info("Skipping completed eAuction batch")
        manifest.upsert_batch({**manifest.get_batch(batch_id), "batch_id": batch_id, "status": BATCH_STATUS_SKIPPED})
        return 0

    if include_auction_ids is not None and not include_auction_ids:
        export = AuctionsExport(
            generated_at=datetime.now(IST),
            count=0,
            auctions=[],
            stats={"deep_parse_filter_enabled": True, "deep_parse_ids_requested": 0},
        )
        _write_batch_export(out_path, export)
        manifest.mark_done(batch_id, source="eauction", output_file=output_file, auction_count=0, lot_count=0)
        logger.info("eAuction skipped: no deep-parse IDs")
        return 0

    manifest.mark_running(batch_id, source="eauction", output_file=output_file)
    warnings: list[str] = []
    try:
        rows, ea_stats = scrape_eauction_tabs(
            tabs=list(EAUCTION_TABS),
            max_pages=None,
            enrich_details=True,
            include_auction_ids=include_auction_ids,
        )
    except Exception as exc:
        manifest.mark_failed(batch_id, str(exc), source="eauction", output_file=output_file)
        return 0

    if ea_stats.get("blockers"):
        warnings.append(f"blockers: {ea_stats.get('blockers')}")

    records = [adapt_eauction_record(row) for row in rows]
    records = [r for r in records if not should_exclude_category(r.asset_category, source="eauction")]
    min_closing = parse_min_closing_date(min_closing_date)
    records, filter_stats = apply_future_filter(records, min_closing)

    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(records),
        auctions=records,
        stats={
            **ea_stats,
            "warnings": warnings,
            "future_filter": filter_stats,
            "deep_parse_filter_enabled": include_auction_ids is not None,
            "deep_parse_ids_requested": len(include_auction_ids) if include_auction_ids is not None else None,
        },
    )
    _write_batch_export(out_path, export)
    manifest.mark_done(
        batch_id,
        source="eauction",
        output_file=output_file,
        auction_count=export.count,
        lot_count=sum(len(r.lots) for r in records),
        pages_fetched=ea_stats.get("pages_fetched"),
        detail_success=ea_stats.get("detail_success"),
        detail_fail=ea_stats.get("detail_fail"),
        warnings=warnings,
        future_filter=filter_stats,
    )
    logger.info("eAuction done: %d auctions", export.count)
    return export.count


def batch_run(
    *,
    sources: list[str],
    batch_dir: Path,
    pdf_dir: Path,
    docs_dir: Path,
    thumbs_dir: Path,
    min_closing_date: str,
    max_docs_per_run: int,
    resume: bool,
    force: bool,
    skip_docs: bool = False,
    work_plan_path: Path | None = None,
) -> BatchManifest:
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_dir / "manifest.json"
    manifest = BatchManifest.load_or_create(manifest_path, min_closing_date=min_closing_date)
    manifest.data["docs_budget_remaining"] = max_docs_per_run
    deep_parse_ids: dict[str, set[str]] = {}
    mstc_ids_by_office: dict[str, set[str]] = {}
    if work_plan_path:
        work_plan = load_work_plan(work_plan_path)
        deep_parse_ids = ids_by_source_for_action(work_plan, "deep_parse")
        mstc_ids_by_office = mstc_ids_by_office_for_action(work_plan, "deep_parse")
        manifest.data["incremental_work_plan"] = {
            "path": str(work_plan_path),
            "action_counts": work_plan.action_counts,
            "enabled": True,
        }
        manifest.save()

    if "mstc" in sources:
        docs_remaining = max_docs_per_run
        offices_to_run = OFFICE_CODES
        if work_plan_path:
            if mstc_ids_by_office:
                offices_to_run = [office for office in OFFICE_CODES if office in mstc_ids_by_office]
            elif not deep_parse_ids.get("mstc"):
                offices_to_run = []
        for office in offices_to_run:
            if resume and _batch_done(manifest, f"mstc_{office}", batch_dir, force=force):
                logger.info("Resume: skip MSTC %s", office)
                continue
            used = run_mstc_office_batch(
                office=office,
                batch_dir=batch_dir,
                manifest=manifest,
                pdf_dir=pdf_dir,
                docs_dir=docs_dir,
                thumbs_dir=thumbs_dir,
                min_closing_date=min_closing_date,
                max_docs_per_run=docs_remaining,
                force=force,
                skip_docs=skip_docs,
                include_auction_ids=(
                    mstc_ids_by_office.get(office) or deep_parse_ids.get("mstc")
                    if work_plan_path
                    else None
                ),
            )
            if used:
                batch = manifest.get_batch(f"mstc_{office}") or {}
                docs = batch.get("documents") or {}
                attempted = docs.get("attempted", 0)
                docs_remaining = max(0, docs_remaining - attempted)
                manifest.data["docs_budget_remaining"] = docs_remaining
                manifest.save()

        # One more pass for offices that failed on transient MSTC timeouts.
        failed_offices = [
            office
            for office in offices_to_run
            if (manifest.get_batch(f"mstc_{office}") or {}).get("status") == BATCH_STATUS_FAILED
        ]
        if failed_offices:
            logger.warning("Retrying failed MSTC offices once: %s", ", ".join(failed_offices))
            time.sleep(5)
            for office in failed_offices:
                used = run_mstc_office_batch(
                    office=office,
                    batch_dir=batch_dir,
                    manifest=manifest,
                    pdf_dir=pdf_dir,
                    docs_dir=docs_dir,
                    thumbs_dir=thumbs_dir,
                    min_closing_date=min_closing_date,
                    max_docs_per_run=docs_remaining,
                    force=True,
                    skip_docs=skip_docs,
                    include_auction_ids=(
                        mstc_ids_by_office.get(office) or deep_parse_ids.get("mstc")
                        if work_plan_path
                        else None
                    ),
                )
                if used:
                    batch = manifest.get_batch(f"mstc_{office}") or {}
                    docs = batch.get("documents") or {}
                    attempted = docs.get("attempted", 0)
                    docs_remaining = max(0, docs_remaining - attempted)
                    manifest.data["docs_budget_remaining"] = docs_remaining
                    manifest.save()

    if "gem_forward" in sources:
        if not (resume and _batch_done(manifest, GEM_BATCH_ID, batch_dir, force=force)):
            run_gem_batch(
                batch_dir=batch_dir,
                manifest=manifest,
                min_closing_date=min_closing_date,
                force=force,
                include_auction_ids=deep_parse_ids.get("gem_forward") if work_plan_path else None,
            )

    if "eauction" in sources:
        if not (resume and _batch_done(manifest, EAUCTION_BATCH_ID, batch_dir, force=force)):
            run_eauction_batch(
                batch_dir=batch_dir,
                manifest=manifest,
                min_closing_date=min_closing_date,
                force=force,
                include_auction_ids=deep_parse_ids.get("eauction") if work_plan_path else None,
            )

    logger.info("Batch run complete: %s", json.dumps(manifest.summary()))
    return manifest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Resumable batch auction scraper")
    parser.add_argument("--sources", default="mstc,gem_forward,eauction")
    parser.add_argument("--min-closing-date", required=True)
    parser.add_argument("--batch-dir", type=Path, default=Path("work/batches"))
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--thumbs-dir", type=Path, default=DEFAULT_THUMBS_DIR)
    parser.add_argument("--max-docs-per-run", type=int, default=2000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-run completed batches")
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--work-plan", type=Path, help="Incremental work plan; only deep_parse IDs are parsed")
    args = parser.parse_args(argv)

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    try:
        batch_run(
            sources=sources,
            batch_dir=args.batch_dir,
            pdf_dir=args.pdf_dir,
            docs_dir=args.docs_dir,
            thumbs_dir=args.thumbs_dir,
            min_closing_date=args.min_closing_date,
            max_docs_per_run=args.max_docs_per_run,
            resume=args.resume,
            force=args.force,
            skip_docs=args.skip_docs,
            work_plan_path=args.work_plan,
        )
        return 0
    except Exception as exc:
        logger.exception("batch_run failed: %s", exc)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
