from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter

from scraper.batch_manifest import BATCH_STATUS_DONE, BatchManifest
from scraper.export_guard import write_auctions_json
from scraper.filters import apply_future_filter, parse_min_closing_date
from scraper.models import AuctionRecord, AuctionsExport

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.merge_batches")

_record_adapter = TypeAdapter(AuctionRecord)


def _stable_key(record: AuctionRecord) -> str:
    source = record.source or "mstc"
    sid = record.source_auction_id or record.id
    return f"{source}:{sid}"


def _dedupe_records(records: list[AuctionRecord]) -> tuple[list[AuctionRecord], int]:
    seen: dict[str, AuctionRecord] = {}
    duplicates = 0
    for record in records:
        key = _stable_key(record)
        if key in seen:
            duplicates += 1
            continue
        seen[key] = record
    return list(seen.values()), duplicates


def _count_by(records: list[AuctionRecord], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value = getattr(record, field, None) or "unknown"
        counter[str(value)] += 1
    return dict(counter)


def _aggregate_documents(batch_stats: list[dict]) -> dict:
    totals: dict[str, int] = Counter()
    failed_by_reason: Counter[str] = Counter()
    failed_by_doc_type: Counter[str] = Counter()
    for stats in batch_stats:
        docs = stats.get("documents") or {}
        for key in ("refs_found", "attempted", "downloaded", "cache_hits", "thumbnails_ready", "failed", "skipped_due_limit"):
            totals[key] += int(docs.get(key, 0) or 0)
        for reason, count in (docs.get("failed_by_reason") or {}).items():
            failed_by_reason[reason] += int(count)
        for dtype, count in (docs.get("failed_by_doc_type") or {}).items():
            failed_by_doc_type[dtype] += int(count)
    return {
        **dict(totals),
        "failed_by_reason": dict(failed_by_reason),
        "failed_by_doc_type": dict(failed_by_doc_type),
    }


def load_batch_records(path: Path) -> tuple[list[AuctionRecord], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = [_record_adapter.validate_python(a) for a in data.get("auctions", [])]
    return records, data.get("stats", {})


def merge_batches(
    *,
    batch_dir: Path,
    out_path: Path,
    min_closing_date: str | None,
) -> AuctionsExport:
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = BatchManifest.load_or_create(manifest_path)
    min_closing = parse_min_closing_date(min_closing_date) if min_closing_date else None

    all_records: list[AuctionRecord] = []
    batch_stats: list[dict] = []
    manifest_summary: list[dict] = []

    for batch in manifest.data.get("batches", []):
        manifest_summary.append(
            {
                "batch_id": batch.get("batch_id"),
                "source": batch.get("source"),
                "status": batch.get("status"),
                "auction_count": batch.get("auction_count"),
            }
        )
        if batch.get("status") != BATCH_STATUS_DONE:
            continue
        output_file = batch.get("output_file")
        if not output_file:
            continue
        path = batch_dir / output_file
        if not path.is_file():
            logger.warning("Missing batch file for %s: %s", batch.get("batch_id"), path)
            continue
        records, stats = load_batch_records(path)
        all_records.extend(records)
        batch_stats.append(stats)

    before_dedupe = len(all_records)
    all_records, duplicate_count = _dedupe_records(all_records)
    all_records, filter_stats = apply_future_filter(all_records, min_closing)
    all_records.sort(key=lambda r: r.closing or datetime.min.replace(tzinfo=IST))

    documents = _aggregate_documents(batch_stats)
    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(all_records),
        auctions=all_records,
        stats={
            "by_source": _count_by(all_records, "source"),
            "by_category": _count_by(all_records, "asset_category"),
            "by_region": _count_by(all_records, "region"),
            "by_state": _count_by(all_records, "state"),
            "total_lots_in_export": sum(len(r.lots) for r in all_records),
            "records_before_dedupe": before_dedupe,
            "duplicates_removed": duplicate_count,
            "future_filter": filter_stats,
            "min_closing_date": min_closing_date,
            "documents": documents,
            "batch_manifest_summary": manifest_summary,
            "manifest_status_counts": manifest.summary(),
        },
    )

    payload = export.model_dump(mode="json")
    write_auctions_json(out_path, payload)
    logger.info(
        "Merged %d auctions (%d lots) -> %s",
        export.count,
        export.stats["total_lots_in_export"],
        out_path,
    )
    return export


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Merge completed batch JSON files")
    parser.add_argument("--batch-dir", type=Path, default=Path("work/batches"))
    parser.add_argument("--out", type=Path, default=Path("work/future_full_auctions.json"))
    parser.add_argument("--min-closing-date", required=True)
    args = parser.parse_args(argv)

    try:
        merge_batches(
            batch_dir=args.batch_dir,
            out_path=args.out,
            min_closing_date=args.min_closing_date,
        )
        return 0
    except Exception as exc:
        logger.exception("merge_batches failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
