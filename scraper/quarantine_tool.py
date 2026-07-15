"""CLI for auction quarantine escape hatch."""

from __future__ import annotations

import argparse
import json
import sys

from scraper.auction_quarantine import (
    DEFAULT_AUTO_HOURS,
    MAX_MANUAL_HOURS,
    add_quarantine_entries,
    list_quarantine,
    remove_quarantine_entries,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage auction_quarantine.json on Hostinger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="Quarantine one or more stable keys")
    add_p.add_argument("--key", action="append", required=True, help="stable key e.g. mstc:588636")
    add_p.add_argument("--reason", default="operator_skip")
    add_p.add_argument("--hours", type=int, default=DEFAULT_AUTO_HOURS, help=f"TTL hours (max {MAX_MANUAL_HOURS})")
    add_p.add_argument("--source", default="manual")
    add_p.add_argument("--local-only", action="store_true", help="Do not push to Hostinger")

    list_p = sub.add_parser("list", help="List active quarantine entries")
    list_p.add_argument("--local-only", action="store_true")

    rm_p = sub.add_parser("remove", help="Remove quarantine keys")
    rm_p.add_argument("--key", action="append", required=True)
    rm_p.add_argument("--local-only", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "add":
        hours = min(max(1, int(args.hours)), MAX_MANUAL_HOURS)
        q = add_quarantine_entries(
            args.key,
            reason=args.reason,
            source=args.source,
            hours=hours,
            push_remote=not args.local_only,
        )
        print(json.dumps(q, indent=2, default=str))
        return 0

    if args.cmd == "list":
        q = list_quarantine(pull_remote=not args.local_only)
        print(json.dumps(q, indent=2, default=str))
        return 0

    if args.cmd == "remove":
        q = remove_quarantine_entries(args.key, push_remote=not args.local_only)
        print(json.dumps(q, indent=2, default=str))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
