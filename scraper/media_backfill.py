"""One-shot recovery: re-cache missing lot documents and push media to Hostinger.

Do not run against production until operator says deploy12 (or equivalent).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import requests

from scraper.asset_integrity import find_missing_assets
from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_JSON_OUT,
    DEFAULT_THUMBS_DIR,
    REPO_ROOT,
)
from scraper.document_cache import process_auction_documents
from scraper.finalize_public_export import remove_missing_local_asset_links
from scraper.models import AuctionRecord, AuctionsExport
from scraper.raw_store import push_public_media

logger = logging.getLogger("scraper.media_backfill")


def _auction_needs_backfill(auction: dict, *, public_dir: Path) -> bool:
    for lot in auction.get("lots") or []:
        if not isinstance(lot, dict):
            continue
        for doc in lot.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            status = doc.get("status")
            if status in {"pending", "pending_cache", "failed", "skipped"}:
                if doc.get("filename") or doc.get("source_url"):
                    return True
            for field in ("cached_url", "thumbnail_url"):
                url = doc.get(field)
                if not url:
                    continue
                rel = str(url).lstrip("/")
                if rel.startswith(("docs/", "thumbs/", "pdfs/")) and not (
                    public_dir / rel
                ).is_file():
                    return True
    return False


def run_media_backfill(
    *,
    json_path: Path = DEFAULT_JSON_OUT,
    docs_dir: Path = DEFAULT_DOCS_DIR,
    thumbs_dir: Path = DEFAULT_THUMBS_DIR,
    max_docs: int = 500,
    auction_ids: set[str] | None = None,
    push_media: bool = True,
    public_dir: Path | None = None,
) -> dict:
    public_dir = public_dir or (json_path.parent.parent)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    export = AuctionsExport.model_validate(data)
    stats: dict = {
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
        }
    }
    session = requests.Session()
    remaining = max_docs
    updated: list[AuctionRecord] = []
    hydrated_ids: set[str] = set()
    budget_exhausted = False
    for record in export.auctions:
        raw = record.model_dump(mode="json")
        include = True
        if auction_ids is not None:
            include = str(record.id) in auction_ids
        elif not _auction_needs_backfill(raw, public_dir=public_dir):
            include = False
        if not include or budget_exhausted:
            updated.append(record)
            continue
        hydrated_ids.add(str(record.id))
        refreshed, remaining = process_auction_documents(
            record,
            docs_dir=docs_dir,
            thumbs_dir=thumbs_dir,
            skip_docs=False,
            max_docs_remaining=remaining,
            session=session,
            stats=stats,
        )
        updated.append(refreshed)
        if remaining <= 0:
            budget_exhausted = True
            logger.info("doc budget exhausted after %s auctions", len(hydrated_ids))

    export = export.model_copy(update={"auctions": updated, "stats": dict(export.stats or {})})
    export.stats = dict(export.stats or {})
    export.stats["documents"] = stats["documents"]
    export.stats["media_backfill"] = {
        "targeted": len(hydrated_ids),
        "hydrated_ids": sorted(hydrated_ids)[:50],
        "max_docs": max_docs,
        "docs_downloaded": stats["documents"].get("downloaded"),
        "thumbnails_ready": stats["documents"].get("thumbnails_ready"),
    }
    payload = export.model_dump(mode="json")

    # Scrub ONLY hydrated auctions — never the whole export against a sparse disk.
    removed = {"pdfs": 0, "docs": 0, "thumbs": 0}
    if hydrated_ids:
        subset = {
            "auctions": [
                a
                for a in (payload.get("auctions") or [])
                if isinstance(a, dict) and str(a.get("id")) in hydrated_ids
            ]
        }
        removed = remove_missing_local_asset_links(subset, public_dir=public_dir)
    payload["stats"] = dict(payload.get("stats") or {})
    payload["stats"]["missing_local_asset_links_removed"] = sum(removed.values())
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    media = None
    if push_media:
        media = push_public_media(public_dir=public_dir)
        logger.info("media push: %s", media.to_dict())

    orphan_sample = [
        m
        for m in find_missing_assets(payload, public_dir=public_dir)
        if m.auction_id in hydrated_ids
    ]
    result = {
        "targeted": len(hydrated_ids),
        "hydrated_ids": sorted(hydrated_ids),
        "docs_stats": stats["documents"],
        "removed": removed,
        "orphan_refs_after_for_hydrated": len(orphan_sample),
        "media_push": media.to_dict() if media else None,
        "json_path": str(json_path),
    }
    logger.info("media_backfill done: %s", result)
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Backfill missing lot docs/thumbs")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--thumbs-dir", type=Path, default=DEFAULT_THUMBS_DIR)
    parser.add_argument("--max-docs", type=int, default=500)
    parser.add_argument(
        "--auction-id",
        action="append",
        default=[],
        help="Limit to auction id(s); repeatable (e.g. 589631)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip Hostinger media push (local hydrate only)",
    )
    args = parser.parse_args(argv)
    ids = set(args.auction_id) if args.auction_id else None
    run_media_backfill(
        json_path=args.json,
        docs_dir=args.docs_dir,
        thumbs_dir=args.thumbs_dir,
        max_docs=args.max_docs,
        auction_ids=ids,
        push_media=not args.no_push,
        public_dir=REPO_ROOT / "web" / "public",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
