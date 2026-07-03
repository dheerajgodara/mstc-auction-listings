"""Hydrate lot document metadata from files already on disk."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scraper.document_cache import process_auction_documents
from scraper.merger import refresh_auction_emd_fields
from scraper.models import AuctionRecord, AuctionsExport

logger = logging.getLogger(__name__)


def hydrate_export_documents(
    export_path: Path,
    *,
    docs_dir: Path,
    thumbs_dir: Path,
    max_docs_per_run: int = 200,
    refresh_emd: bool = True,
) -> AuctionsExport:
    data = json.loads(export_path.read_text(encoding="utf-8"))
    export = AuctionsExport.model_validate(data)
    stats = dict(export.stats or {})
    stats["documents"] = {
        "refs_found": 0,
        "attempted": 0,
        "downloaded": 0,
        "cache_hits": 0,
        "thumbnails_ready": 0,
        "failed": 0,
        "skipped_due_limit": 0,
        "failed_by_reason": {},
        "failed_by_doc_type": {},
    }
    updated: list[AuctionRecord] = []
    remaining = max_docs_per_run
    for record in export.auctions:
        working = refresh_auction_emd_fields(record) if refresh_emd else record
        refreshed, remaining = process_auction_documents(
            working,
            docs_dir=docs_dir,
            thumbs_dir=thumbs_dir,
            skip_docs=False,
            max_docs_remaining=remaining,
            session=None,
            stats=stats,
        )
        updated.append(refreshed)
    export = export.model_copy(update={"auctions": updated, "stats": stats})
    export_path.write_text(
        json.dumps(export.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return export


def main(argv: list[str] | None = None) -> int:
    from scraper.config import DEFAULT_DOCS_DIR, DEFAULT_JSON_OUT, DEFAULT_THUMBS_DIR

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Hydrate cached lot documents into auctions.json")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--thumbs-dir", type=Path, default=DEFAULT_THUMBS_DIR)
    parser.add_argument("--max-docs-per-run", type=int, default=200)
    parser.add_argument("--skip-emd-refresh", action="store_true")
    args = parser.parse_args(argv)

    export = hydrate_export_documents(
        args.json,
        docs_dir=args.docs_dir,
        thumbs_dir=args.thumbs_dir,
        max_docs_per_run=args.max_docs_per_run,
        refresh_emd=not args.skip_emd_refresh,
    )
    docs = export.stats.get("documents", {})
    logger.info(
        "Hydration complete: auctions=%d docs_stats=%s",
        export.count,
        docs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
