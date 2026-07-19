"""Job 3: Build + verify + deploy ready export to Hostinger."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.asset_bootstrap import bootstrap_production_assets
from scraper.ai_enrichment.cache_sync import pull_remote_ai_cache
from scraper.ai_enrichment.hydrate import hydrate_json_file
from scraper.config import AI_ENRICHMENT_CACHE_DIR, DEFAULT_JSON_OUT, REPO_ROOT, SITE_BASE_URL
from scraper.deploy import deploy as deploy_to_hostinger
from scraper.document_cache import migrate_unsafe_thumb_dirs
from scraper.export_hygiene import repair_absolute_asset_paths, rewrite_unsafe_thumb_urls
from scraper.filters import make_run_id, tomorrow_min_closing_date
from scraper.http_verify import verify_live_site
from scraper.pipeline_ledger import DEFAULT_LEDGER_PATH, load_ledger, pull_ledger
from scraper.pipeline_markers import LAST_DEPLOY_MARKER, pull_pipeline_json, push_pipeline_json
from scraper.predeploy_verify import verify_predeploy_build
from scraper.raw_store import push_public_media
from scraper.refresh_and_deploy import _bootstrap_previous_production_from_live
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_telegram_report
from scraper.verify_fail_extract import summarize_command_failure

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_deploy")


def _github_run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def _setup_logging(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(run_dir / "deploy.log", encoding="utf-8"),
        ],
        force=True,
    )


def _run(cmd: list[str], *, cwd: Path) -> None:
    logger.info("Running: %s (cwd=%s)", " ".join(cmd), cwd)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        short, fails, tail = summarize_command_failure(
            cmd,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
        if fails:
            logger.error("Command failed with FAIL lines: %s", "; ".join(fails))
        if tail.strip():
            logger.error("Command output tail:\n%s", tail[-2000:])
        raise RuntimeError(short)


def _export_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_pipeline_deploy(
    *,
    repo_root: Path = REPO_ROOT,
    deploy: bool = True,
    break_stale_lock: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    run_id = f"deploy_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)

    lock_path = repo_root / "work" / "deploy.lock"
    acquire_refresh_lock(lock_path=lock_path, run_id=run_id, stale_minutes=180, break_stale_lock=break_stale_lock)

    production_json = Path(DEFAULT_JSON_OUT)
    public_dir = repo_root / "web" / "public"
    web_dir = repo_root / "web"
    out_dir = web_dir / "out"

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "deploy",
        "started_at": started,
        "deploy_requested": deploy,
        "force": force,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="deploy_started")

    warnings: list[str] = []
    try:
        _bootstrap_previous_production_from_live(
            production_json=production_json,
            base_url=SITE_BASE_URL or None,
            warnings=warnings,
        )
        if not production_json.is_file() or production_json.stat().st_size < 10:
            raise RuntimeError("no auctions.json available for deploy")

        cache_pull = pull_remote_ai_cache(cache_dir=AI_ENRICHMENT_CACHE_DIR)
        payload["ai_cache_pull"] = cache_pull.to_dict()
        if not cache_pull.ok:
            warnings.append(f"ai cache pull failed: {cache_pull.message}")
        elif cache_pull.message == "remote AI cache pulled":
            warnings.append(
                f"ai cache pull ok ({cache_pull.file_count} file(s) from {cache_pull.remote_path})"
            )
        elif cache_pull.file_count:
            warnings.append(
                f"ai cache using local/GHA copy ({cache_pull.file_count} file(s); {cache_pull.message})"
            )

        hydrate_result = hydrate_json_file(
            production_json,
            cache_dir=AI_ENRICHMENT_CACHE_DIR,
            write=True,
        )
        payload["ai_hydrate"] = hydrate_result
        ai_stats = hydrate_result.get("stats") or {}
        if ai_stats.get("ready"):
            warnings.append(f"ai hydrate merged {ai_stats.get('ready')} ready listing(s) into export")

        export_sha = _export_sha256(production_json)
        payload["export_sha256"] = export_sha
        remote_marker = pull_pipeline_json(LAST_DEPLOY_MARKER) or {}
        if (
            deploy
            and not force
            and remote_marker.get("export_sha") == export_sha
            and remote_marker.get("ok") is True
        ):
            pull_ledger(local_path=DEFAULT_LEDGER_PATH)
            ledger = load_ledger(DEFAULT_LEDGER_PATH)
            payload.update(
                {
                    "status": "success",
                    "finished_at": datetime.now(IST).isoformat(),
                    "deploy_skipped_unchanged": True,
                    "deploy": {"attempted": False, "ok": True, "skipped": True},
                    "ledger": ledger.status_counts(),
                    "warnings": warnings,
                    "auctions": (json.loads(production_json.read_text(encoding="utf-8")).get("count")),
                }
            )
            (run_dir / "deploy_report.json").write_text(
                json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
            )
            send_telegram_report(payload, event="deploy_done")
            return payload

        asset_boot = bootstrap_production_assets(public_dir=public_dir)
        payload["asset_bootstrap"] = asset_boot.to_dict()
        # Migrate unsafe lot thumb dirs before media push / build.
        migrate_stats = migrate_unsafe_thumb_dirs(public_dir / "thumbs")
        if migrate_stats.get("renamed") or migrate_stats.get("merged"):
            warnings.append(
                "thumb lot migrate: "
                f"renamed={migrate_stats.get('renamed', 0)} "
                f"merged={migrate_stats.get('merged', 0)}"
            )
            payload["thumb_lot_migrate"] = migrate_stats
        # Safety-net: push any local docs/thumbs/pdfs parse may have left unsynced.
        media_push = push_public_media(public_dir=public_dir)
        payload["media_push"] = media_push.to_dict()
        if media_push.attempted and not media_push.ok:
            warnings.append(f"deploy media push partial/failed: {media_push.message}")
        elif media_push.ok:
            warnings.append("deploy media push ok")
        pull_ledger(local_path=DEFAULT_LEDGER_PATH)
        ledger = load_ledger(DEFAULT_LEDGER_PATH)
        payload["ledger"] = ledger.status_counts()

        if production_json.is_file():
            try:
                raw = json.loads(production_json.read_text(encoding="utf-8"))
                repaired = repair_absolute_asset_paths(raw)
                url_stats = rewrite_unsafe_thumb_urls(repaired.export)
                if repaired.repaired or url_stats.get("rewritten"):
                    production_json.write_text(
                        json.dumps(repaired.export, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    if repaired.repaired:
                        warnings.append(
                            f"repaired {len(repaired.repaired)} absolute asset path(s) before build"
                        )
                        payload["repaired_absolute_paths"] = len(repaired.repaired)
                    if url_stats.get("rewritten"):
                        warnings.append(
                            f"rewrote {url_stats['rewritten']} unsafe thumb URL(s) before build"
                        )
                        payload["thumb_url_rewrite"] = url_stats
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append(f"pre-build asset repair skipped: {exc}")

        _run(["pnpm", "run", "build:prod"], cwd=web_dir)
        _run(["pnpm", "run", "verify-build"], cwd=web_dir)

        predeploy = verify_predeploy_build(
            out_dir=out_dir,
            min_count=1000,
            min_closing_date=tomorrow_min_closing_date(),
            require_sources=["mstc"],
            warn_only_sources=["gem_forward", "eauction"],
        )
        payload["predeploy"] = {
            "passed": predeploy.passed,
            "count": predeploy.count,
            "by_source": predeploy.by_source,
            "errors": predeploy.errors,
            "warnings": predeploy.warnings,
        }
        warnings.extend(predeploy.warnings)
        if not predeploy.passed:
            raise RuntimeError(f"predeploy verify failed: {predeploy.errors}")

        deploy_info: dict[str, Any] = {"attempted": False, "ok": False}
        if deploy:
            deploy_to_hostinger(build_dir=out_dir)
            deploy_info = {"attempted": True, "ok": True}
            http = verify_live_site(
                base_url=SITE_BASE_URL or None,
                expected_count=predeploy.count,
                candidate_json=production_json,
                output_assets_dir=public_dir,
            )
            payload["http_verify"] = {
                "passed": http.passed,
                "errors": http.errors,
                "warnings": http.warnings,
                "checked_urls": http.checked_urls,
            }
            warnings.extend(http.warnings)
            if not http.passed:
                raise RuntimeError(f"live HTTP verify failed: {http.errors}")
            push_pipeline_json(
                LAST_DEPLOY_MARKER,
                {
                    "export_sha": export_sha,
                    "deployed_at": datetime.now(IST).isoformat(),
                    "run_id": run_id,
                    "ok": True,
                    "count": predeploy.count,
                },
            )

        payload.update(
            {
                "status": "success",
                "finished_at": datetime.now(IST).isoformat(),
                "deploy": deploy_info,
                "deploy_skipped_unchanged": False,
                "warnings": warnings,
                "auctions": predeploy.count,
                "by_source": predeploy.by_source,
            }
        )
        (run_dir / "deploy_report.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        send_telegram_report(payload, event="deploy_done")
        return payload
    except Exception as exc:
        logger.exception("pipeline deploy failed")
        payload["status"] = "failed"
        payload["errors"] = [str(exc)]
        payload["warnings"] = warnings
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="deploy_failed")
        raise
    finally:
        release_refresh_lock(lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline job 3: build and deploy")
    parser.add_argument("--no-deploy", action="store_true", help="Build/verify only")
    parser.add_argument("--force", action="store_true", help="Deploy even if export fingerprint unchanged")
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_pipeline_deploy(
        deploy=not args.no_deploy,
        break_stale_lock=args.break_stale_lock,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
