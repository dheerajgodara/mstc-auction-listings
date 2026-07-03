"""Helpers for cleaning cached lot documents outside the retention window.

Not invoked automatically by the scraper pipeline. Run manually when needed.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_stale_document_dirs(
    *,
    active_auction_ids: set[str],
    docs_dir: Path,
    thumbs_dir: Path,
    dry_run: bool = True,
) -> dict[str, int]:
    """Remove docs/thumbs folders for auctions no longer in the export."""
    removed_docs = 0
    removed_thumbs = 0

    for base, counter_name in ((docs_dir, "removed_docs"), (thumbs_dir, "removed_thumbs")):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            auction_id = child.name
            if auction_id in active_auction_ids:
                continue
            logger.info("%s remove %s", "Would" if dry_run else "Removing", child)
            if not dry_run:
                shutil.rmtree(child, ignore_errors=True)
            if counter_name == "removed_docs":
                removed_docs += 1
            else:
                removed_thumbs += 1

    return {"removed_docs": removed_docs, "removed_thumbs": removed_thumbs}


def load_active_auction_ids(json_path: Path) -> set[str]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    auctions = data.get("auctions") or []
    ids: set[str] = set()
    for auction in auctions:
        auction_id = auction.get("id")
        if auction_id:
            ids.add(str(auction_id))
        source_id = auction.get("source_auction_id")
        if source_id:
            ids.add(str(source_id))
    return ids


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Clean stale cached lot documents")
    parser.add_argument("--json", type=Path, required=True, help="Path to auctions.json export")
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--thumbs-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true", help="Actually delete stale directories")
    args = parser.parse_args(argv)

    if not args.json.is_file():
        logger.error("JSON file not found: %s", args.json)
        return 1

    active_ids = load_active_auction_ids(args.json)
    dry_run = not args.apply
    result = cleanup_stale_document_dirs(
        active_auction_ids=active_ids,
        docs_dir=args.docs_dir,
        thumbs_dir=args.thumbs_dir,
        dry_run=dry_run,
    )
    logger.info(
        "%s cleanup complete: removed_docs=%d removed_thumbs=%d active_auctions=%d",
        "Dry-run" if dry_run else "Apply",
        result["removed_docs"],
        result["removed_thumbs"],
        len(active_ids),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
