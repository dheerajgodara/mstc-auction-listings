from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.config import REPO_ROOT
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
    finalized = finalize_export_payload(
        json.loads(json.dumps(previous)),
        previous_export=previous,
        automation_ran_at=automation_ran_at,
        run_id=run_id,
        history_path=history_path,
    )
    missing_pdf_count = remove_missing_local_pdf_links(finalized, public_dir=json_path.parent.parent)
    if missing_pdf_count:
        stats = dict(finalized.get("stats") or {})
        stats["missing_local_pdf_links_removed"] = missing_pdf_count
        finalized["stats"] = stats
    json_path.write_text(json.dumps(finalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(
        "Finalized %s (%d auctions, run_id=%s)",
        json_path,
        finalized.get("count"),
        finalized.get("run_id"),
    )
    return finalized


def remove_missing_local_pdf_links(export: dict, *, public_dir: Path) -> int:
    """Remove local pdf_url values that do not exist in web/public.

    Incremental discovery can safely publish listing-only records before their
    catalogue PDF has been deep-scraped. Those records must not point at
    `pdfs/*.pdf` until the file exists, otherwise build/deploy verification
    correctly refuses the export. External/source links are preserved.
    """
    removed = 0
    for auction in export.get("auctions", []) or []:
        pdf_url = auction.get("pdf_url")
        if not _is_local_pdf_url(pdf_url):
            continue
        rel = str(pdf_url).lstrip("/")
        if (public_dir / rel).is_file():
            continue
        auction["pdf_url"] = None
        warnings = list(auction.get("warnings") or [])
        note = f"local PDF not cached yet: {rel}"
        if note not in warnings:
            warnings.append(note)
        auction["warnings"] = warnings
        document_urls = auction.get("document_urls")
        if isinstance(document_urls, list):
            auction["document_urls"] = [url for url in document_urls if str(url).lstrip("/") != rel]
        removed += 1
    return removed


def _is_local_pdf_url(value: object) -> bool:
    if not value:
        return False
    text = str(value)
    return text.startswith("pdfs/") or text.startswith("/pdfs/")


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
