"""Rewrite Hostinger ledger to v3 and re-queue unfinished work.

Never deletes identity rows. Maps v2 PDF/sync fields into hostinger_doc_*.
Sets stages so shells must Download→Parse again before publish.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.config import PDF_DETAIL_URL, SITE_BASE_URL
from scraper.pipeline_ledger import (
    ACTIVE_SOURCES,
    DEFAULT_LEDGER_PATH,
    LEDGER_SCHEMA_VERSION,
    LedgerItem,
    PipelineLedger,
    empty_ledger,
    load_ledger,
    public_doc_url,
    pull_ledger,
    push_ledger,
    write_ledger,
)

IST = ZoneInfo("Asia/Kolkata")


def _now() -> str:
    return datetime.now(IST).isoformat()


def migrate_raw_item(raw: dict) -> LedgerItem | None:
    source = str(raw.get("source") or "").strip().lower()
    aid = str(raw.get("source_auction_id") or "").strip()
    key = str(raw.get("stable_key") or "").strip()
    if not key and source and aid:
        key = f"{source}:{aid}"
    if not key or not source or not aid:
        return None
    if source not in ACTIVE_SOURCES:
        return None

    portal = (raw.get("portal_doc_url") or "").strip() or None
    if not portal:
        if source == "mstc":
            portal = PDF_DETAIL_URL
        else:
            for d in raw.get("document_urls") or []:
                if isinstance(d, str) and d.strip():
                    portal = d.strip()
                    break
            portal = portal or (raw.get("source_pdf_url") or "").strip() or None

    # Prefer v3 fields, else map v2 pdf_path + media_synced
    host_path = (raw.get("hostinger_doc_path") or "").strip() or None
    host_url = (raw.get("hostinger_doc_url") or "").strip() or None
    pdf_path = (raw.get("pdf_path") or "").strip() or None
    media_synced = raw.get("media_synced")
    if not host_path and pdf_path:
        host_path = pdf_path
    if host_path and not host_url:
        host_url = public_doc_url(host_path, site_base=SITE_BASE_URL or None)

    has_hostinger = bool(host_path and host_url and media_synced is not False)
    # If v2 said media_synced True with pdf_path, trust Hostinger
    if pdf_path and media_synced is True:
        has_hostinger = True
        host_path = host_path or pdf_path
        host_url = host_url or public_doc_url(host_path)

    lots_count = int(raw.get("lots_count") or 0)
    parse_done = raw.get("parse") == "done" and lots_count > 0
    # Re-queue parse unless we already have lots_count from prior parse artifact knowledge
    if raw.get("parse") == "done" and lots_count <= 0:
        parse_done = False

    if not portal:
        download_status = "blocked"
        parse_status = "blocked"
        discover_status = "failed"
        discover_error = "missing portal_doc_url"
    else:
        discover_status = "done"
        discover_error = None
        if has_hostinger:
            download_status = "done"
            parse_status = "done" if parse_done else "pending"
        else:
            download_status = "pending"
            parse_status = "pending"

    return LedgerItem(
        stable_key=key,
        source=source,
        source_auction_id=aid,
        portal_doc_url=portal,
        hostinger_doc_path=host_path if has_hostinger else None,
        hostinger_doc_url=host_url if has_hostinger else None,
        doc_sha256=(raw.get("doc_sha256") or raw.get("pdf_sha256") or None),
        discover=discover_status,
        download=download_status,
        parse=parse_status,
        deploy="pending",  # force re-publish only after publishable gate
        discover_error=discover_error,
        # Reset attempts for unfinished stages so cutover re-queue is actionable.
        download_attempts=0 if not has_hostinger else int(raw.get("download_attempts") or 0),
        parse_attempts=0 if not parse_done else int(raw.get("parse_attempts") or 0),
        closing=raw.get("closing"),
        opening=raw.get("opening"),
        seller=raw.get("seller"),
        state=raw.get("state"),
        detail_url=raw.get("detail_url"),
        priority_score=int(raw.get("priority_score") or 0),
        lots_count=lots_count if parse_done else 0,
        parsed_path=raw.get("parsed_path") if parse_done else None,
        raw_html_path=raw.get("raw_html_path"),
        removed_from_source=bool(raw.get("removed_from_source") or False),
        first_seen_at=str(raw.get("first_seen_at") or raw.get("first_queued_at") or _now()),
        updated_at=_now(),
    )


def migrate_to_v3(path: Path) -> PipelineLedger:
    if not path.is_file():
        return empty_ledger()
    raw = json.loads(path.read_text(encoding="utf-8"))
    items_in = raw.get("items") or []
    out = empty_ledger()
    by_key: dict[str, LedgerItem] = {}
    for row in items_in:
        if not isinstance(row, dict):
            continue
        item = migrate_raw_item(row)
        if item is None:
            continue
        by_key[item.stable_key] = item
    out.items = sorted(by_key.values(), key=lambda i: (-i.priority_score, i.stable_key))
    out.version = LEDGER_SCHEMA_VERSION
    out.schema_version = LEDGER_SCHEMA_VERSION
    out.generated_at = _now()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate pipeline_ledger.json to v3 (re-queue)")
    parser.add_argument("--path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--backup", action="store_true", default=True)
    args = parser.parse_args(argv)

    if args.pull:
        pull_ledger(local_path=args.path)

    if args.path.is_file() and args.backup:
        bak = args.path.with_name(args.path.stem + f".v2.bak.json")
        shutil.copy2(args.path, bak)
        print(f"backup: {bak}")

    # Prefer raw JSON migration so v2 extras survive mapping
    ledger = migrate_to_v3(args.path) if args.path.is_file() else empty_ledger()
    # If file was already partially readable as v3, still rewrite clean
    if not ledger.items and args.path.is_file():
        ledger = load_ledger(args.path)

    write_ledger(ledger, args.path)
    counts = ledger.status_counts()
    print(
        f"v3 items={counts['total']} publishable={counts['publishable']} "
        f"download={counts.get('download')} parse={counts.get('parse')}"
    )

    if args.push:
        push_ledger(local_path=args.path)
        print("pushed Hostinger ledger")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
