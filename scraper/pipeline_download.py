"""Job 1: Download raw HTML / PDFs / docs into durable storage (no parse/deploy)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from scraper.asset_bootstrap import bootstrap_production_assets
from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_JSON_OUT,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    DEFAULT_THUMBS_DIR,
    PIPELINE_DOWNLOAD_CAP_CATCHUP,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.document_cache import process_auction_documents
from scraper.discovery import run_discovery
from scraper.filters import make_run_id, tomorrow_min_closing_date
from scraper.import_tracking import stable_auction_key
from scraper.incremental import load_export
from scraper.incremental_plan import build_work_plan
from scraper.main import enrich_auction, listing_to_base, resolve_auction_listing
from scraper.models import AuctionRecord, ExtractionStatus
from scraper.pipeline_ledger import (
    estimated_download_runs_to_clear,
    load_ledger,
    mark_download,
    pull_ledger,
    push_ledger,
    select_for_download,
    upsert_from_work_plan,
    write_ledger,
)
from scraper.media_sync import media_push_required
from scraper.pdf_downloader import validate_pdf_file
from scraper.pipeline_markers import reset_download_retry_state
from scraper.raw_store import (
    has_raw_html,
    pull_raw_store,
    push_public_media,
    push_raw_store,
    raw_html_rel_path,
)
from scraper.refresh_and_deploy import _bootstrap_previous_production_from_live
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.schedule_guard import latest_slot_start
from scraper.telegram_reporter import send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_download")


def _phase(msg: str) -> None:
    print(f"[pipeline_download] {msg}", flush=True)
    logger.info(msg)


def _setup_logging(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "download.log"
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


def _discovery_by_key(discovery: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for auction in discovery.get("auctions") or []:
        out[stable_auction_key(auction)] = auction
    return out


def _base_from_discovery(auction: dict[str, Any]) -> AuctionRecord:
    aid = str(auction.get("source_auction_id") or auction.get("id") or "")
    try:
        return AuctionRecord.model_validate(auction)
    except Exception:
        base, _ = resolve_auction_listing(aid)
        return base


def run_pipeline_download(
    *,
    repo_root: Path = REPO_ROOT,
    max_download: int = PIPELINE_DOWNLOAD_CAP_CATCHUP,
    max_docs_per_run: int = 2000,
    sources: list[str] | None = None,
    skip_docs: bool = False,
    skip_pdf: bool = False,
    force_min_closing_date: str | None = None,
    break_stale_lock: bool = True,
) -> dict[str, Any]:
    import os

    sources = sources or ["mstc", "gem_forward", "eauction"]
    run_id = f"download_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)

    lock_path = repo_root / "work" / "download.lock"
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
    docs_dir = Path(DEFAULT_DOCS_DIR)
    thumbs_dir = Path(DEFAULT_THUMBS_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "download",
        "started_at": started,
        "min_closing_date": min_closing,
        "max_download": max_download,
        "sources": sources,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="download_started")

    warnings: list[str] = []
    errors: list[str] = []
    try:
        _bootstrap_previous_production_from_live(
            production_json=production_json,
            base_url=SITE_BASE_URL or None,
            warnings=warnings,
        )
        bootstrap_production_assets(public_dir=public_dir)
        pull_raw_store(raw_dir=raw_dir)
        pull_ledger(local_path=ledger_path)

        previous_export = load_export(production_json)
        if not previous_export or int(previous_export.get("count") or 0) <= 0:
            raise RuntimeError("download job requires bootstrapped previous production export")

        discovery_path = run_dir / "discovery_latest.json"
        discovery_export = run_discovery(
            sources=sources,
            out_path=discovery_path,
            min_closing_date=min_closing,
            allow_small_output=True,
        )
        discovery_data = discovery_export.model_dump(mode="json") if hasattr(discovery_export, "model_dump") else json.loads(
            discovery_path.read_text(encoding="utf-8")
        )
        # Prefer file content for consistency
        if discovery_path.is_file():
            discovery_data = json.loads(discovery_path.read_text(encoding="utf-8"))

        plan = build_work_plan(discovery_data, previous_export)
        deep_items = [i for i in plan.items if i.action == "deep_parse"]
        ledger = load_ledger(ledger_path)
        ledger = upsert_from_work_plan(
            ledger,
            deep_items=deep_items,
            previous_export=previous_export,
            public_dir=public_dir,
        )
        selected = select_for_download(ledger, limit=max_download, pdf_dir=pdf_dir)
        write_ledger(ledger, ledger_path)

        payload["discovery"] = {
            "total": discovery_data.get("count") or len(discovery_data.get("auctions") or []),
            "by_source": ((discovery_data.get("stats") or {}).get("by_source") or {}),
        }
        payload["ledger"] = ledger.status_counts()
        payload["selected_count"] = len(selected)
        payload["estimated_runs_to_clear"] = estimated_download_runs_to_clear(
            ledger, cap=max_download, pdf_dir=pdf_dir
        )
        send_telegram_report(payload, event="download_selection")

        by_disc = _discovery_by_key(discovery_data)
        stats: dict[str, Any] = {
            "html_downloaded": 0,
            "html_failures": 0,
            "pdf_downloaded": 0,
            "pdf_cache_hits": 0,
            "pdf_failures": 0,
            "pdf_failed_ids": [],
            "documents": {},
        }
        docs_remaining = max_docs_per_run
        session = requests.Session()
        ok_count = 0
        fail_count = 0
        last_ledger_push_ok = 0
        loop_started = time.monotonic()
        total_selected = len(selected)

        for idx, item in enumerate(selected, start=1):
            # Non-MSTC: mark download done if we at least capture listing; deep assets via full enrich later in parse.
            if item.source != "mstc":
                # Leave gem/eauction for parse job (needs live enrich). Mark download pending→special handled in parse.
                # For ledger progress, treat as downloaded placeholder when discovery row exists.
                if item.stable_key in by_disc:
                    mark_download(
                        ledger,
                        item.stable_key,
                        ok=True,
                        error=None,
                    )
                    # Force parse pending for non-MSTC so parse job deep-enriches.
                    li = ledger.by_key().get(item.stable_key)
                    if li and li.parse == "done":
                        li.parse = "pending"
                        li.deploy_ready = False
                    ok_count += 1
                else:
                    mark_download(ledger, item.stable_key, ok=False, error="missing from discovery")
                    fail_count += 1
            else:
                disc = by_disc.get(item.stable_key) or {}
                base = _base_from_discovery(disc) if disc else resolve_auction_listing(item.source_auction_id)[0]
                base.source = "mstc"
                try:
                    downloaded = enrich_auction(
                        base,
                        pdf_dir=pdf_dir,
                        skip_pdf=skip_pdf,
                        stats=stats,
                        mode="download_only",
                        raw_dir=raw_dir,
                    )
                    if not skip_docs and docs_remaining > 0:
                        # Docs need lot refs from parse; skip heavy doc hydrate in download-only
                        # unless lots somehow already present.
                        if downloaded.lots:
                            downloaded, docs_remaining = process_auction_documents(
                                downloaded,
                                docs_dir=docs_dir,
                                thumbs_dir=thumbs_dir,
                                skip_docs=False,
                                max_docs_remaining=docs_remaining,
                                session=session,
                                stats=stats,
                            )
                    has_html = has_raw_html("mstc", item.source_auction_id, raw_dir=raw_dir)
                    has_pdf = validate_pdf_file(pdf_dir / f"{item.source_auction_id}.pdf")
                    # Foolproof MSTC download: HTML + valid catalogue PDF required
                    # (unless --skip-pdf for local debugging).
                    if skip_pdf:
                        ok = has_html
                    else:
                        ok = has_html and has_pdf
                    err = None
                    if not ok:
                        parts = list(downloaded.errors or [])
                        if not has_html:
                            parts.append("missing raw HTML")
                        if not skip_pdf and not has_pdf:
                            parts.append("missing or invalid catalogue PDF")
                        err = "; ".join(parts) if parts else "download incomplete"
                    mark_download(
                        ledger,
                        item.stable_key,
                        ok=ok,
                        raw_html_path=raw_html_rel_path("mstc", item.source_auction_id) if has_html else None,
                        pdf_path=f"pdfs/{item.source_auction_id}.pdf" if has_pdf else None,
                        error=err,
                    )
                    if ok:
                        ok_count += 1
                    else:
                        fail_count += 1
                except Exception as exc:
                    logger.exception("download failed for %s", item.stable_key)
                    mark_download(ledger, item.stable_key, ok=False, error=str(exc))
                    fail_count += 1

            if idx % 25 == 0 or idx == total_selected:
                elapsed = max(time.monotonic() - loop_started, 0.001)
                rate = ok_count / (elapsed / 60.0)
                _phase(
                    f"progress {idx}/{total_selected} ok={ok_count} failed={fail_count} "
                    f"elapsed_min={elapsed/60:.1f} ok_per_min={rate:.1f}"
                )
            if ok_count >= last_ledger_push_ok + 50:
                write_ledger(ledger, ledger_path)
                push_ledger(local_path=ledger_path)
                last_ledger_push_ok = ok_count
                _phase(f"mid-run ledger push at ok={ok_count}")

        write_ledger(ledger, ledger_path)
        push_raw_store(raw_dir=raw_dir)
        _phase("media: pushing pdfs/docs/thumbs to Hostinger")
        media_result = push_public_media(public_dir=public_dir)
        payload["media_push"] = media_result.to_dict()
        if media_result.ok:
            warnings.append("media push ok")
        else:
            warnings.append(f"media push failed: {media_result.message}")
            # Foolproof Hostinger save: never report success if PDFs were not synced.
            if (
                not skip_pdf
                and media_push_required()
                and ok_count > 0
                and not media_result.ok
            ):
                raise RuntimeError(
                    f"download media push failed (PDFs not confirmed on Hostinger): "
                    f"{media_result.message}"
                )
        push_ledger(local_path=ledger_path)

        finished = datetime.now(IST).isoformat()
        wall_seconds = time.monotonic() - loop_started
        # Reset fast-retry budget after a successful download job.
        try:
            slot = latest_slot_start(datetime.now(IST)).strftime("%Y-%m-%dT%H:%M%z")
            reset_download_retry_state(slot_id=slot)
        except Exception as exc:
            warnings.append(f"reset download retry state failed: {exc}")

        payload.update(
            {
                "status": "success",
                "finished_at": finished,
                "download_ok": ok_count,
                "download_failed": fail_count,
                "stats": stats,
                "ledger": ledger.status_counts(),
                "warnings": warnings,
                "docs_budget_left": docs_remaining,
                "estimated_runs_to_clear": estimated_download_runs_to_clear(
                    ledger, cap=max_download, pdf_dir=pdf_dir
                ),
                "wall_seconds": round(wall_seconds, 1),
                "ok_per_min": round(ok_count / (wall_seconds / 60.0), 2) if wall_seconds > 0 else None,
            }
        )
        (run_dir / "download_report.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        send_telegram_report(payload, event="download_done")
        return payload
    except Exception as exc:
        logger.exception("pipeline download failed")
        errors.append(str(exc))
        payload["status"] = "failed"
        payload["errors"] = errors
        payload["warnings"] = warnings
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="download_failed")
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline job 1: download raw assets")
    parser.add_argument("--max-download", type=int, default=PIPELINE_DOWNLOAD_CAP_CATCHUP)
    parser.add_argument("--max-docs-per-run", type=int, default=2000)
    parser.add_argument("--sources", default="mstc,gem_forward,eauction")
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--min-closing-date", default=None)
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    run_pipeline_download(
        max_download=args.max_download,
        max_docs_per_run=args.max_docs_per_run,
        sources=sources,
        skip_docs=args.skip_docs,
        skip_pdf=args.skip_pdf,
        force_min_closing_date=args.min_closing_date,
        break_stale_lock=args.break_stale_lock,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
