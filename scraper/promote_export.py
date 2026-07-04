from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.export_guard import ExportGuardError, is_protected_export_path, validate_export_write
from scraper.import_tracking import finalize_export_payload
from scraper.qa_summary import run_strict_qa

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.promote_export")


def promote_export(
    *,
    candidate: Path,
    target: Path,
    min_count: int,
    min_closing_date: str,
    backup_dir: Path,
    require_sources: list[str] | None = None,
    warn_missing_sources: list[str] | None = None,
    allow_small_output: bool = False,
    automation_ran_at: datetime | None = None,
    run_id: str | None = None,
    history_path: Path | None = None,
) -> Path:
    if not candidate.is_file():
        raise FileNotFoundError(f"Candidate not found: {candidate}")

    qa = run_strict_qa(
        candidate,
        min_count=min_count,
        min_closing_date=min_closing_date,
        require_sources=require_sources or ["mstc", "eauction"],
        warn_missing_sources=warn_missing_sources if warn_missing_sources is not None else ["gem_forward"],
    )
    if not qa["passed"]:
        raise ExportGuardError(f"QA failed, refusing promotion: {qa.get('strict_errors', qa.get('errors', []))}")

    data = json.loads(candidate.read_text(encoding="utf-8"))
    count = data.get("count", len(data.get("auctions", [])))
    validate_export_write(target, count, allow_small_output=allow_small_output)

    previous_export = None
    if target.is_file():
        previous_export = json.loads(target.read_text(encoding="utf-8"))

    resolved_history = history_path or target.parent / "import-history.json"
    data = finalize_export_payload(
        data,
        previous_export=previous_export,
        automation_ran_at=automation_ran_at,
        run_id=run_id,
        history_path=resolved_history,
    )
    count = data.get("count", len(data.get("auctions", [])))

    if not is_protected_export_path(target):
        logger.warning("Target %s is not a known protected path; proceeding with caution", target)

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if target.is_file():
        stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"auctions_{stamp}.json"
        shutil.copy2(target, backup_path)
        logger.info("Backed up existing export to %s", backup_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        tmp.write(json.dumps(data, indent=2, ensure_ascii=False))
        tmp_path = Path(tmp.name)
    tmp_path.replace(target)
    logger.info("Promoted %s -> %s (%d auctions)", candidate, target, count)
    return backup_path or target


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Promote QA-passed candidate to production JSON")
    parser.add_argument("--candidate", type=Path, default=Path("work/future_full_auctions.json"))
    parser.add_argument("--target", type=Path, default=Path("web/public/data/auctions.json"))
    parser.add_argument("--min-count", type=int, default=1000)
    parser.add_argument("--min-closing-date", required=True)
    parser.add_argument("--backup-dir", type=Path, default=Path("work/backups"))
    parser.add_argument("--require-sources", default="mstc,eauction")
    parser.add_argument("--allow-small-output", action="store_true")
    args = parser.parse_args(argv)

    require_sources = [s.strip() for s in args.require_sources.split(",") if s.strip()]
    try:
        promote_export(
            candidate=args.candidate,
            target=args.target,
            min_count=args.min_count,
            min_closing_date=args.min_closing_date,
            backup_dir=args.backup_dir,
            require_sources=require_sources,
            allow_small_output=args.allow_small_output,
        )
        return 0
    except ExportGuardError as exc:
        logger.error("%s", exc)
        return 2
    except Exception as exc:
        logger.exception("promote_export failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
