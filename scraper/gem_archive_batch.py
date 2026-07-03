"""Process pending GeM premium auctions one at a time."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scraper.config import REPO_ROOT
from scraper.gem_analysis.archive_pipeline import run_archive_pipeline
from scraper.gem_analysis.catalog_store import get_archive_catalog
from scraper.gem_analysis.tender_ingest import ingest_auction
from scraper.gem_reports_deploy import deploy

WORK = REPO_ROOT / "work"
PREMIUM_JSON = WORK / "gem_premium_auctions.json"
ARCHIVE_DIR = WORK / "gem_premium_analysis"
CHECKPOINT = WORK / "gem_archive_checkpoint.json"


def _pending_ids() -> list[str]:
    data = json.loads(PREMIUM_JSON.read_text(encoding="utf-8"))
    ordered = sorted(
        data["auctions"],
        key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or 0),
    )
    done = {p.stem.split("_auction_")[-1].replace("_archive", "") for p in ARCHIVE_DIR.glob("*_archive.json")}
    return [a["auction_id"] for a in ordered if a["auction_id"] not in done]


def _save_checkpoint(auction_id: str, status: str, detail: str = "") -> None:
    state: dict = {}
    if CHECKPOINT.is_file():
        state = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    state[auction_id] = {"status": status, "detail": detail}
    CHECKPOINT.write_text(json.dumps(state, indent=2), encoding="utf-8")


def process_one(auction_id: str, *, deploy_after: bool = False, skip_ingest: bool = False) -> None:
    data = json.loads(PREMIUM_JSON.read_text(encoding="utf-8"))
    record = next((a for a in data["auctions"] if a["auction_id"] == auction_id), None)
    if not record:
        raise ValueError(f"Unknown auction {auction_id}")

    docs = REPO_ROOT / "work" / "gem_premium_docs" / auction_id
    if not skip_ingest and not (docs / "manifest.json").is_file():
        notice = record.get("notice_path") or ""
        if notice:
            ingest_auction(auction_id, notice)

    if not get_archive_catalog(auction_id):
        raise ValueError(f"No catalog for {auction_id} — add work/gem_archive_catalogs/{auction_id}.json or catalogs/{auction_id}.py")

    run_archive_pipeline(auction_id)
    _save_checkpoint(auction_id, "complete")
    if deploy_after:
        deploy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch GeM archive builder")
    parser.add_argument("--auction-id", help="Single auction (default: next pending)")
    parser.add_argument("--list-pending", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args(argv)

    pending = _pending_ids()
    if args.list_pending:
        for i, aid in enumerate(pending, 1):
            print(f"{i:2}. {aid}")
        print(f"Total pending: {len(pending)}")
        return 0

    aid = args.auction_id or (pending[0] if pending else None)
    if not aid:
        print("No pending auctions.")
        return 0

    process_one(aid, deploy_after=args.deploy, skip_ingest=args.skip_ingest)
    print(f"Archive built for {aid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
