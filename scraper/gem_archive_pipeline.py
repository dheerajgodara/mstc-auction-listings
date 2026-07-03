"""GeM premium auction archive — informational reports (no P&L)."""

from __future__ import annotations

import argparse
import sys

from scraper.gem_analysis.archive_pipeline import run_archive_pipeline
from scraper.gem_reports_deploy import deploy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build GeM archive report")
    parser.add_argument("--auction-id", required=True)
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args(argv)

    run_archive_pipeline(args.auction_id)
    if args.deploy:
        deploy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
