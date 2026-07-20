from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.ai_enrichment.hydrate import hydrate_auctions_export
from scraper.asset_integrity import (
    auction_has_missing_document_assets,
    local_asset_kind as _local_asset_kind,
    normalize_rel as _normalize_rel,
    preview_url as _preview_url,
    scrub_export_lot_documents,
)
from scraper.config import AI_ENRICHMENT_CACHE_DIR, REPO_ROOT
from scraper.export_hygiene import repair_absolute_asset_paths
from scraper.import_tracking import finalize_export_payload

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.finalize_public_export")

DEFAULT_JSON = REPO_ROOT / "web" / "public" / "data" / "auctions.json"
DEFAULT_HISTORY = REPO_ROOT / "web" / "public" / "data" / "import-history.json"


def finalize_public_export(
    *,
    json_path: Path = DEFAULT_JSON,
    history_path: Path = DEFAULT_HISTORY,
    automation_ran_at: datetime | None = None,
    run_id: str | None = None,
) -> dict:
    if not json_path.is_file():
        raise FileNotFoundError(f"Export not found: {json_path}")
    if json_path.stat().st_size == 0:
        raise ValueError(
            f"Export is zero bytes: {json_path} — restore from web/out or promote a valid candidate",
        )

    previous = json.loads(json_path.read_text(encoding="utf-8"))
    automation_ran_at = automation_ran_at or datetime.now(IST)
    repaired = repair_absolute_asset_paths(previous)
    previous = repaired.export
    if repaired.repaired:
        logger.info("repaired %s absolute asset path(s) before finalize", len(repaired.repaired))
    hydrated_export, ai_stats = hydrate_auctions_export(previous, cache_dir=AI_ENRICHMENT_CACHE_DIR)
    previous = hydrated_export
    if ai_stats.get("ready"):
        logger.info(
            "merged cached AI enrichment into export (ready=%s missing=%s rejected=%s failed=%s)",
            ai_stats.get("ready"),
            ai_stats.get("missing"),
            ai_stats.get("rejected"),
            ai_stats.get("failed"),
        )
    finalized = finalize_export_payload(
        json.loads(json.dumps(previous)),
        previous_export=previous,
        automation_ran_at=automation_ran_at,
        run_id=run_id,
        history_path=history_path,
    )
    public_dir = json_path.parent.parent
    removed = remove_missing_local_asset_links(finalized, public_dir=public_dir)
    if any(removed.values()):
        stats = dict(finalized.get("stats") or {})
        stats["missing_local_pdf_links_removed"] = removed["pdfs"]
        stats["missing_local_docs_links_removed"] = removed["docs"]
        stats["missing_local_thumbs_links_removed"] = removed["thumbs"]
        stats["missing_local_asset_links_removed"] = sum(removed.values())
        finalized["stats"] = stats
    json_path.write_text(json.dumps(finalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(
        "Finalized %s (%d auctions, run_id=%s, stripped pdfs=%d docs=%d thumbs=%d)",
        json_path,
        finalized.get("count"),
        finalized.get("run_id"),
        removed["pdfs"],
        removed["docs"],
        removed["thumbs"],
    )
    return finalized


def remove_missing_local_pdf_links(export: dict, *, public_dir: Path) -> int:
    """Backward-compatible wrapper: strip missing pdfs/ links only."""
    return remove_missing_local_asset_links(export, public_dir=public_dir)["pdfs"]


def remove_missing_local_asset_links(export: dict, *, public_dir: Path) -> dict[str, int]:
    """Remove local pdfs/, docs/, and thumbs/ URLs that do not exist under public_dir.

    Incremental discovery can publish listing-only records before catalogue media
    is deep-scraped. Those records must not point at missing local paths, otherwise
    build/deploy verification correctly refuses the export. External URLs are kept.
    """
    removed = {"pdfs": 0, "docs": 0, "thumbs": 0}
    for auction in export.get("auctions", []) or []:
        pdf_url = auction.get("pdf_url")
        if _is_local_asset_url(pdf_url, prefix="pdfs/"):
            rel = _normalize_rel(pdf_url)
            if not (public_dir / rel).is_file():
                auction["pdf_url"] = None
                _append_warning(auction, f"local PDF not cached yet: {rel}")
                document_urls = auction.get("document_urls")
                if isinstance(document_urls, list):
                    auction["document_urls"] = [
                        url for url in document_urls if _normalize_rel(url) != rel
                    ]
                removed["pdfs"] += 1

        document_urls = auction.get("document_urls")
        if isinstance(document_urls, list):
            kept_docs: list = []
            for url in document_urls:
                kind = _local_asset_kind(url)
                if kind is None:
                    kept_docs.append(url)
                    continue
                rel = _normalize_rel(url)
                if (public_dir / rel).is_file():
                    kept_docs.append(url)
                    continue
                _append_warning(auction, f"local {kind} asset not cached yet: {rel}")
                removed[kind] += 1
            auction["document_urls"] = kept_docs

        for lot in auction.get("lots") or []:
            if not isinstance(lot, dict):
                continue
            previews = lot.get("preview_images")
            if not isinstance(previews, list):
                continue
            kept_previews: list = []
            for img in previews:
                url = _preview_url(img)
                if url is None:
                    kept_previews.append(img)
                    continue
                kind = _local_asset_kind(url)
                if kind is None:
                    kept_previews.append(img)
                    continue
                rel = _normalize_rel(url)
                if (public_dir / rel).is_file():
                    kept_previews.append(img)
                    continue
                _append_warning(auction, f"local {kind} asset not cached yet: {rel}")
                removed[kind] += 1
            lot["preview_images"] = kept_previews

    # Scrub lot.documents[].cached_url / thumbnail_url and rebuild preview_images.
    lot_doc_removed = scrub_export_lot_documents(export, public_dir=public_dir)
    removed["docs"] += lot_doc_removed["docs"]
    removed["thumbs"] += lot_doc_removed["thumbs"]
    return removed


def auction_has_missing_local_assets(auction: dict, *, public_dir: Path) -> bool:
    """True if auction JSON points at a missing local pdfs/docs/thumbs path."""
    return auction_has_missing_document_assets(auction, public_dir=public_dir)


def _append_warning(auction: dict, note: str) -> None:
    warnings = list(auction.get("warnings") or [])
    if note not in warnings:
        warnings.append(note)
    auction["warnings"] = warnings


def _is_local_asset_url(value: object, *, prefix: str) -> bool:
    if not value:
        return False
    text = str(value).lstrip("/")
    return text.startswith(prefix)


def _is_local_pdf_url(value: object) -> bool:
    return _is_local_asset_url(value, prefix="pdfs/")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Finalize public auctions.json with import tracking")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    try:
        finalize_public_export(
            json_path=args.json,
            history_path=args.history,
            run_id=args.run_id,
        )
        return 0
    except Exception as exc:
        logger.exception("finalize_public_export failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
