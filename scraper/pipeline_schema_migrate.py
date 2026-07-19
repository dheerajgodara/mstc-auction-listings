"""Additive ledger v2 migration — never deletes rows or unknown keys."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.pipeline_ledger import (
    DEFAULT_LEDGER_PATH,
    LEDGER_SCHEMA_VERSION,
    PipelineLedger,
    load_ledger,
    pull_ledger,
    push_ledger,
    write_ledger,
)

IST = ZoneInfo("Asia/Kolkata")


def migrate_ledger(ledger: PipelineLedger) -> PipelineLedger:
    now = datetime.now(IST).isoformat()
    for item in ledger.items:
        if not getattr(item, "discover", None):
            item.discover = "done" if item.first_queued_at else "pending"
        if not getattr(item, "build", None):
            item.build = "done" if item.deploy_ready else "pending"
        if getattr(item, "discover_seen_at", None) is None and item.first_queued_at:
            item.discover_seen_at = item.first_queued_at
        if getattr(item, "removed_from_source", None) is None:
            item.removed_from_source = False
        item.updated_at = item.updated_at or now
    ledger.version = LEDGER_SCHEMA_VERSION
    ledger.generated_at = now
    return ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate pipeline_ledger.json to v2 (additive)")
    parser.add_argument("--path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--pull", action="store_true", help="Pull from Hostinger first")
    parser.add_argument("--push", action="store_true", help="Push to Hostinger after migrate")
    parser.add_argument("--backup", action="store_true", default=True)
    args = parser.parse_args(argv)

    if args.pull:
        pull_ledger(local_path=args.path)

    if args.path.is_file() and args.backup:
        bak = args.path.with_name(args.path.stem + ".v1.bak.json")
        shutil.copy2(args.path, bak)
        print(f"backup: {bak}")

    ledger = load_ledger(args.path)
    before = len(ledger.items)
    ledger = migrate_ledger(ledger)
    write_ledger(ledger, args.path)
    print(f"migrated items={before} version={ledger.version} -> {args.path}")

    if args.push:
        push_ledger(local_path=args.path)
        print("pushed Hostinger ledger")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
