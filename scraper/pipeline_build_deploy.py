"""Independent Build/Deploy lane: merge discovery + parse cache → one site deploy."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import DEFAULT_JSON_OUT, DEFAULT_PARSED_DIR, DEFAULT_PIPELINE_LEDGER, REPO_ROOT
from scraper.export_guard import write_auctions_json
from scraper.filters import make_run_id, tomorrow_min_closing_date
from scraper.import_tracking import stable_auction_key
from scraper.incremental import load_export
from scraper.parse_cache import iter_local_parsed, load_parse_artifact, pull_parsed_tree
from scraper.pipeline_deploy import run_pipeline_deploy
from scraper.pipeline_ledger import load_ledger, pull_ledger, push_ledger, write_ledger
from scraper.pipeline_markers import pull_pipeline_json
from scraper.promote_export import promote_export
from scraper.refresh_and_deploy import _bootstrap_previous_production_from_live
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report
from scraper.config import SITE_BASE_URL

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_build_deploy")


def _phase(msg: str) -> None:
    print(f"[build_deploy] {msg}", flush=True)
    logger.info(msg)


def _load_discovery_snapshots() -> list[dict[str, Any]]:
    auctions: list[dict[str, Any]] = []
    for name in ("discovery_mstc_latest.json", "discovery_gem_latest.json", "discovery_latest.json"):
        data = pull_pipeline_json(name)
        if not data:
            continue
        for a in data.get("auctions") or []:
            if isinstance(a, dict):
                auctions.append(a)
    return auctions


def materialize_from_parse_cache(
    *,
    previous: dict[str, Any],
    parsed_root: Path,
    discovery_auctions: list[dict[str, Any]],
) -> dict[str, Any]:
    prev_idx = {stable_auction_key(a): a for a in previous.get("auctions") or []}
    disc_idx = {stable_auction_key(a): a for a in discovery_auctions}
    out: dict[str, dict[str, Any]] = dict(prev_idx)

    # Overlay discovery listing fields (without wiping lots).
    for key, disc in disc_idx.items():
        base = dict(out.get(key) or disc)
        for fld in (
            "auction_number",
            "opening",
            "closing",
            "state",
            "office",
            "region",
            "detail_url",
            "platform",
            "source",
            "source_auction_id",
            "id",
        ):
            if disc.get(fld) not in (None, ""):
                base[fld] = disc[fld]
        out[key] = base

    ready = 0
    for path in iter_local_parsed(parsed_root):
        art = load_parse_artifact(path)
        if not art:
            continue
        rec = art.get("record")
        if not isinstance(rec, dict):
            continue
        lots = rec.get("lots") or []
        if not isinstance(lots, list) or not lots:
            continue
        key = stable_auction_key(rec)
        merged = dict(out.get(key) or {})
        merged.update(rec)
        meta = art.get("meta") or {}
        merged["enrichment_status"] = "parsed"
        merged["pipeline"] = {
            "parsed_at": meta.get("parsed_at"),
            "pdf_sha256": meta.get("pdf_sha256"),
            "parser_version": meta.get("parser_version"),
        }
        # Prefer non-AI display: clear dependence on ai_* for material search
        out[key] = merged
        ready += 1

    records = [a for a in out.values() if not a.get("removed_from_source")]
    # Drop eAuction from active export when rebuilding
    records = [a for a in records if str(a.get("source") or "") != "eauction"]
    records.sort(key=lambda r: r.get("closing") or "")
    return {
        "generated_at": datetime.now(IST).isoformat(),
        "count": len(records),
        "auctions": records,
        "stats": {"build_ready_from_parse_cache": ready, "by_source": {}},
        "_ready_merged": ready,
    }


def run_build_deploy(
    *,
    repo_root: Path = REPO_ROOT,
    deploy: bool = True,
    break_stale_lock: bool = True,
) -> dict[str, Any]:
    run_id = f"build_deploy_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(run_dir / "build_deploy.log", encoding="utf-8"),
        ],
        force=True,
    )
    lock_path = repo_root / "work" / "build_deploy.lock"
    acquire_refresh_lock(
        lock_path=lock_path, run_id=run_id, stale_minutes=360, break_stale_lock=break_stale_lock
    )

    production_json = Path(DEFAULT_JSON_OUT)
    parsed_root = Path(DEFAULT_PARSED_DIR)
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)

    try:
        warnings: list[str] = []
        _bootstrap_previous_production_from_live(
            production_json=production_json,
            base_url=SITE_BASE_URL or None,
            warnings=warnings,
        )
        pull_ledger(local_path=ledger_path)
        pull_parsed_tree(local_root=parsed_root)
        previous = load_export(production_json) or {"auctions": [], "count": 0}
        discovery_auctions = _load_discovery_snapshots()
        export = materialize_from_parse_cache(
            previous=previous,
            parsed_root=parsed_root,
            discovery_auctions=discovery_auctions,
        )
        ready = int(export.pop("_ready_merged", 0))
        candidate = run_dir / "candidate_auctions.json"
        write_auctions_json(candidate, export, allow_small_output=True)
        backup_dir = repo_root / "work" / "export_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        promote_export(
            candidate=candidate,
            target=production_json,
            min_count=max(50, int((previous.get("count") or 0) * 0.5)),
            min_closing_date=tomorrow_min_closing_date(),
            backup_dir=backup_dir,
            require_sources=["mstc"],
            warn_missing_sources=["gem_forward"],
            allow_small_output=True,
        )

        with_lots = sum(1 for a in export.get("auctions") or [] if a.get("lots"))
        deploy_ok = True
        if deploy:
            # Soft-disable AI hydrate by env for this process
            import os

            os.environ["AI_ENRICHMENT_DISABLE"] = "1"
            run_pipeline_deploy(deploy=True, force=True, break_stale_lock=True)

        # Mark build done for parsed keys
        ledger = load_ledger(ledger_path)
        now = datetime.now(IST).isoformat()
        for a in export.get("auctions") or []:
            if not (a.get("lots") or []):
                continue
            key = stable_auction_key(a)
            item = ledger.by_key().get(key)
            if item is None:
                continue
            item.build = "done"
            item.deploy_ready = True
            item.deployed_at = now
            item.build_last_error = None
        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)

        send_lane_report(
            "build_deploy",
            "finished",
            {
                "status": "Live" if deploy_ok else "Built",
                "ready_merged": ready,
                "export_count": export.get("count"),
                "deploy_ok": deploy_ok and deploy,
                "with_lots_count": with_lots,
            },
            noop=ready == 0,
        )
        return {
            "run_id": run_id,
            "ready_merged": ready,
            "count": export.get("count"),
            "with_lots": with_lots,
        }
    except Exception as exc:
        send_lane_report("build_deploy", "failed", {"error": str(exc)})
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build + deploy lane")
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_build_deploy(deploy=not args.no_deploy, break_stale_lock=args.break_stale_lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
