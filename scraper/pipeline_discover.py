"""Process 0: Discover + bootstrap + ledger queue fill (no PDF download)."""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.asset_bootstrap import bootstrap_production_assets
from scraper.config import (
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    PIPELINE_DOWNLOAD_BATCH_SIZE,
    PIPELINE_DOWNLOAD_CAP_CATCHUP,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.discovery import run_discovery
from scraper.filters import make_run_id, tomorrow_min_closing_date
from scraper.incremental import load_export
from scraper.incremental_plan import build_work_plan
from scraper.import_tracking import stable_auction_key
from scraper.pipeline_ledger import (
    classify_download_queue_item,
    estimated_download_runs_to_clear,
    load_ledger,
    pull_ledger,
    push_ledger,
    select_for_download,
    upsert_from_work_plan,
    write_ledger,
)
from scraper.raw_store import pull_public_pdf_files, pull_raw_store
from scraper.refresh_and_deploy import _bootstrap_previous_production_from_live
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report, send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_discover")


def _phase(msg: str) -> None:
    print(f"[pipeline_discover] {msg}", flush=True)
    logger.info(msg)


def _setup_logging(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "discover.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )


def _github_run_url() -> str | None:
    import os

    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def run_pipeline_discover(
    *,
    repo_root: Path = REPO_ROOT,
    queue_cap: int = PIPELINE_DOWNLOAD_CAP_CATCHUP,
    batch_size: int = PIPELINE_DOWNLOAD_BATCH_SIZE,
    sources: list[str] | None = None,
    force_min_closing_date: str | None = None,
    break_stale_lock: bool = True,
) -> dict[str, Any]:
    sources = sources or ["mstc", "gem_forward", "eauction"]
    run_id = f"discover_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)

    lock_name = "discover.lock"
    if sources == ["mstc"]:
        lock_name = "discover_mstc.lock"
    elif sources == ["gem_forward"]:
        lock_name = "discover_gem.lock"
    lock_path = repo_root / "work" / lock_name
    acquire_refresh_lock(
        lock_path=lock_path,
        run_id=run_id,
        stale_minutes=360,
        break_stale_lock=break_stale_lock,
    )

    min_closing = force_min_closing_date or tomorrow_min_closing_date()
    production_json = repo_root / "web" / "public" / "data" / "auctions.json"
    public_dir = repo_root / "web" / "public"
    pdf_dir = Path(DEFAULT_PDF_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    batch_size = max(1, int(batch_size))
    queue_cap = max(1, int(queue_cap))

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "discover",
        "started_at": started,
        "min_closing_date": min_closing,
        "queue_cap": queue_cap,
        "batch_size": batch_size,
        "sources": sources,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="discover_started")

    warnings: list[str] = []
    errors: list[str] = []
    try:
        pdf_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        _bootstrap_previous_production_from_live(
            production_json=production_json,
            base_url=SITE_BASE_URL or None,
            warnings=warnings,
        )
        boot = bootstrap_production_assets(public_dir=public_dir, dirs=("docs", "thumbs"))
        if boot.warnings:
            warnings.extend(boot.warnings)
        _phase(boot.message)
        pull_raw_store(raw_dir=raw_dir)
        pull_ledger(local_path=ledger_path)

        previous_export: dict[str, Any] | None = None
        if production_json.is_file():
            try:
                previous_export = load_export(production_json)
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append(f"discover: could not read previous export: {exc}")
                previous_export = None
        if not previous_export:
            previous_export = {
                "auctions": [],
                "count": 0,
                "generated_at": datetime.now(IST).isoformat(),
            }
            _phase("discover: empty previous export (v3 cutover / first run)")
            production_json.parent.mkdir(parents=True, exist_ok=True)
            if not production_json.is_file():
                production_json.write_text(
                    json.dumps(previous_export, indent=2) + "\n", encoding="utf-8"
                )

        discovery_path = run_dir / "discovery_latest.json"
        discovery_export = run_discovery(
            sources=sources,
            out_path=discovery_path,
            min_closing_date=min_closing,
            allow_small_output=True,
        )
        discovery_data = (
            discovery_export.model_dump(mode="json")
            if hasattr(discovery_export, "model_dump")
            else json.loads(discovery_path.read_text(encoding="utf-8"))
        )
        if discovery_path.is_file():
            discovery_data = json.loads(discovery_path.read_text(encoding="utf-8"))

        # Per-source Hostinger snapshots (independent Discover lanes).
        from scraper.parse_cache import push_discovery_snapshot

        src_set = {s.strip().lower() for s in sources}
        if src_set == {"mstc"}:
            snap_name = "discovery_mstc_latest.json"
            lane_id = "discover_mstc"
        elif src_set == {"gem_forward"}:
            snap_name = "discovery_gem_latest.json"
            lane_id = "discover_gem"
        else:
            snap_name = "discovery_latest.json"
            lane_id = "discover_mstc" if "mstc" in src_set else "discover_gem"
        snap_path = run_dir / snap_name
        snap_payload = dict(discovery_data)
        snap_payload["schema_version"] = 1
        if len(src_set) == 1:
            snap_payload["source"] = next(iter(src_set))
        snap_path.write_text(json.dumps(snap_payload, indent=2, default=str) + "\n", encoding="utf-8")
        push_discovery_snapshot(snap_path, snap_name)
        plan = build_work_plan(discovery_data, previous_export)
        # Upsert every listing in this discovery snapshot so portal_doc_url heals even
        # when the work-plan marks rows unchanged (critical for GeM after v3 migrate).
        from types import SimpleNamespace

        discovery_by_key = {
            stable_auction_key(a): a
            for a in (discovery_data.get("auctions") or [])
            if isinstance(a, dict)
        }
        deep_items = []
        for key, auction in discovery_by_key.items():
            aid = str(auction.get("source_auction_id") or auction.get("id") or "")
            if ":" in aid and aid.split(":", 1)[0] in {"mstc", "gem_forward", "eauction"}:
                aid = aid.split(":", 1)[-1]
            deep_items.append(
                SimpleNamespace(
                    stable_key=key,
                    source=str(auction.get("source") or "mstc").strip().lower(),
                    source_auction_id=aid,
                    decision="changed",
                    action="deep_parse",
                    metadata=auction,
                )
            )
        if not deep_items:
            deep_items = [i for i in plan.items if i.action == "deep_parse"]
        ledger = load_ledger(ledger_path)
        ledger = upsert_from_work_plan(
            ledger,
            deep_items=deep_items,
            previous_export=previous_export,
            public_dir=public_dir,
            discovery_by_key=discovery_by_key,
        )
        missing_docs = sum(1 for i in ledger.items if i.discover == "failed")
        if missing_docs:
            _phase(f"ledger: {missing_docs} row(s) failed discover (missing portal_doc_url)")
        # Preview who would be selected for download (cap = queue_cap).
        src_filter = next(iter(src_set)) if len(src_set) == 1 else "mstc"
        queued = select_for_download(
            ledger, limit=queue_cap, pdf_dir=pdf_dir, source=src_filter
        )
        if len(src_set) == 1 and src_filter == "gem_forward":
            pass
        elif len(src_set) > 1:
            queued = select_for_download(ledger, limit=queue_cap, pdf_dir=pdf_dir, source="mstc")
            queued += select_for_download(
                ledger, limit=max(1, queue_cap - len(queued)), pdf_dir=pdf_dir, source="gem_forward"
            )
        write_ledger(ledger, ledger_path)

        # Selective Hostinger PDF pull for queued MSTC IDs only (cache warm for Process 1).
        if queued:
            pdf_names = [f"{i.source_auction_id}.pdf" for i in queued if i.source == "mstc"]
            _phase(f"media: selective PDF pull for {len(pdf_names)} queued MSTC id(s)")
            pull_result = pull_public_pdf_files(public_dir=public_dir, filenames=pdf_names)
            payload["pdf_selective_pull"] = pull_result.to_dict()
            if pull_result.warnings:
                warnings.extend(pull_result.warnings)
            _phase(pull_result.message)

        push_ledger(local_path=ledger_path)

        queued_count = len(queued)
        queued_new = sum(1 for i in queued if classify_download_queue_item(i) == "new")
        queued_sync = sum(1 for i in queued if classify_download_queue_item(i) == "sync")
        queued_repair = sum(1 for i in queued if classify_download_queue_item(i) == "repair")
        est_batches = int(math.ceil(queued_count / batch_size)) if queued_count else 0
        finished = datetime.now(IST).isoformat()
        payload.update(
            {
                "status": "success",
                "finished_at": finished,
                "discovery": {
                    "total": discovery_data.get("count")
                    or len(discovery_data.get("auctions") or []),
                    "by_source": ((discovery_data.get("stats") or {}).get("by_source") or {}),
                },
                "queued_count": queued_count,
                "queued_new": queued_new,
                "queued_sync": queued_sync,
                "queued_repair": queued_repair,
                "discover_missing_portal_doc": missing_docs,
                "estimated_download_batches": est_batches,
                "estimated_runs_to_clear": estimated_download_runs_to_clear(
                    ledger, cap=batch_size, pdf_dir=pdf_dir
                ),
                "ledger": ledger.status_counts(),
                "warnings": warnings,
            }
        )
        (run_dir / "discover_report.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        event = "discover_empty" if queued_count == 0 else "discover_done"
        send_telegram_report(payload, event=event)
        listed = int(payload["discovery"]["total"] or 0)
        send_lane_report(
            lane_id,
            "finished",
            {
                "status": "Done",
                "listed": listed,
                "new": queued_new,
                "queued_download": queued_count,
                "unchanged": max(0, listed - queued_new),
                "cap": queue_cap,
                "snapshot": snap_name,
            },
            noop=queued_count == 0 and listed == 0,
        )
        _phase(
            f"done queued={queued_count} batches≈{est_batches} "
            f"discovery_total={payload['discovery']['total']}"
        )
        return payload
    except Exception as exc:
        logger.exception("pipeline discover failed")
        errors.append(str(exc))
        payload["status"] = "failed"
        payload["errors"] = errors
        payload["warnings"] = warnings
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="discover_failed")
        srcs = sources or []
        fail_lane = (
            "discover_mstc"
            if srcs == ["mstc"]
            else "discover_gem"
            if srcs == ["gem_forward"]
            else "discover_mstc"
        )
        send_lane_report(
            fail_lane,
            "failed",
            {"error": str(exc), "backlog_left": "?"},
        )
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline discover lane (source-filtered)")
    parser.add_argument("--queue-cap", type=int, default=PIPELINE_DOWNLOAD_CAP_CATCHUP)
    parser.add_argument("--batch-size", type=int, default=PIPELINE_DOWNLOAD_BATCH_SIZE)
    parser.add_argument("--sources", default="mstc,gem_forward")
    parser.add_argument("--min-closing-date", default=None)
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    run_pipeline_discover(
        queue_cap=args.queue_cap,
        batch_size=args.batch_size,
        sources=sources,
        force_min_closing_date=args.min_closing_date,
        break_stale_lock=args.break_stale_lock,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
