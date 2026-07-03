"""CLI for GeM premium auction analysis pipeline."""

from __future__ import annotations

import argparse
import sys

from scraper.gem_analysis.pipeline import run_pipeline
from scraper.gem_reports_deploy import deploy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GeM premium auction analysis")
    parser.add_argument("--auction-id", required=True)
    parser.add_argument("--full", action="store_true", help="Build analysis + HTML")
    parser.add_argument("--deploy", action="store_true", help="Deploy to Hostinger after build")
    args = parser.parse_args(argv)

    if args.full:
        run_pipeline(args.auction_id, html=True)
    else:
        run_pipeline(args.auction_id, html=False)

    if args.deploy:
        deploy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
