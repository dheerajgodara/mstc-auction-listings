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

    previous = json.loads(json_path.read_text(encoding="utf-8"))
    automation_ran_at = automation_ran_at or datetime.now(IST)
    finalized = finalize_export_payload(
        json.loads(json.dumps(previous)),
        previous_export=previous,
        automation_ran_at=automation_ran_at,
        run_id=run_id,
        history_path=history_path,
    )
    json_path.write_text(json.dumps(finalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(
        "Finalized %s (%d auctions, run_id=%s)",
        json_path,
        finalized.get("count"),
        finalized.get("run_id"),
    )
    return finalized


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
