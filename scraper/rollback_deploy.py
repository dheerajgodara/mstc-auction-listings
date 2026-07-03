from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.config import DEFAULT_JSON_OUT, REPO_ROOT, SITE_BASE_URL
from scraper.deploy import deploy as deploy_to_hostinger
from scraper.http_verify import verify_live_site
from scraper.refresh_reports import load_production_summary, update_latest_run

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.rollback_deploy")


def list_backups(backup_dir: Path) -> list[Path]:
    if not backup_dir.is_dir():
        return []
    return sorted(backup_dir.glob("auctions_*.json"), reverse=True)


def restore_backup(
    *,
    backup: Path,
    target: Path,
    backup_dir: Path,
) -> Path:
    if not backup.is_file():
        raise FileNotFoundError(f"Backup not found: {backup}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        pre_restore = backup_dir / f"auctions_pre_rollback_{stamp}.json"
        shutil.copy2(target, pre_restore)
        logger.info("Saved pre-rollback copy to %s", pre_restore)
    shutil.copy2(backup, target)
    logger.info("Restored %s -> %s", backup, target)
    return target


def rollback_deploy(
    *,
    backup: Path,
    deploy: bool,
    repo_root: Path = REPO_ROOT,
) -> dict:
    production_json = repo_root / DEFAULT_JSON_OUT
    web_dir = repo_root / "web"
    out_dir = web_dir / "out"
    backup_dir = repo_root / "work" / "backups"

    summary_before = load_production_summary(production_json)
    restore_backup(backup=backup, target=production_json, backup_dir=backup_dir)
    summary_after = load_production_summary(production_json)

    result: dict = {
        "backup_restored": str(backup),
        "summary_before": summary_before,
        "summary_after": summary_after,
        "build": None,
        "deploy": None,
        "http_verify": None,
    }

    build_cmd = ["pnpm", "run", "build:prod"]
    verify_cmd = ["pnpm", "run", "verify-build"]
    proc = subprocess.run(build_cmd, cwd=web_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"build:prod failed: {(proc.stderr or '')[-1000:]}")
    proc2 = subprocess.run(verify_cmd, cwd=web_dir, capture_output=True, text=True)
    if proc2.returncode != 0:
        raise RuntimeError(f"verify-build failed: {(proc2.stderr or '')[-1000:]}")
    result["build"] = {"ok": True}

    if deploy:
        deploy_to_hostinger(build_dir=out_dir)
        result["deploy"] = {"deployed": True}
        http = verify_live_site(
            base_url=SITE_BASE_URL or None,
            expected_count=summary_after.get("count"),
            candidate_json=production_json,
        )
        result["http_verify"] = {
            "passed": http.passed,
            "errors": http.errors,
            "warnings": http.warnings,
            "index_status": http.index_status,
        }
        if not http.passed:
            raise RuntimeError(f"HTTP verification failed: {http.errors}")
    else:
        result["deploy"] = {"deployed": False, "skipped": True}

    payload = {
        "run_id": f"rollback_{datetime.now(IST).strftime('%Y%m%d_%H%M%S_IST')}",
        "status": "rollback_success",
        "started_at": datetime.now(IST).isoformat(),
        "finished_at": datetime.now(IST).isoformat(),
        "rollback_backup_path": str(backup),
        "total_auctions": summary_after.get("count"),
        "by_source": summary_after.get("by_source"),
        "deploy": result.get("deploy"),
    }
    update_latest_run(runs_root=repo_root / "work" / "runs", payload=payload, success=True)
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Rollback production auctions.json and optionally redeploy")
    parser.add_argument("--backup", type=Path, help="Backup JSON to restore")
    parser.add_argument("--list", action="store_true", help="List recent backups")
    parser.add_argument("--deploy", action="store_true", help="Rebuild and deploy after restore")
    parser.add_argument("--backup-dir", type=Path, default=Path("work/backups"))
    args = parser.parse_args(argv)

    if args.list:
        backups = list_backups(args.backup_dir)
        if not backups:
            print("No backups found.")
            return 0
        for path in backups[:20]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                count = data.get("count", len(data.get("auctions", [])))
            except (json.JSONDecodeError, OSError):
                count = "?"
            print(f"{path.name}\tcount={count}")
        return 0

    if not args.backup:
        parser.error("--backup is required unless --list is used")

    try:
        result = rollback_deploy(backup=args.backup, deploy=args.deploy)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        logger.exception("rollback failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
