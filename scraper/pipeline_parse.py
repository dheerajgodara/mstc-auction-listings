"""Job 2: Parse downloaded raw HTML/PDFs into clean auction JSON (no site deploy)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.asset_bootstrap import bootstrap_production_assets
from scraper.auction_quarantine import (
    DEFAULT_AUTO_HOURS,
    active_quarantine_keys,
    add_quarantine_entries,
    load_quarantine,
)
from scraper.finalize_public_export import remove_missing_local_asset_links
from scraper.media_sync import export_needs_media_push, media_push_required
from scraper.raw_store import push_public_media
from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_JSON_OUT,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    DEFAULT_THUMBS_DIR,
    PIPELINE_PARSE_CAP_DEFAULT,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.discovery import run_discovery
from scraper.document_cache import migrate_unsafe_thumb_dirs, process_auction_documents
from scraper.export_guard import write_auctions_json
from scraper.export_hygiene import (
    apply_quarantine_skips,
    classify_strict_errors,
    extract_record_keys_from_errors,
    format_dropped_telegram_note,
    format_quarantine_telegram_note,
    format_repair_telegram_note,
    is_record_recoverable,
    repair_absolute_asset_paths,
    rewrite_unsafe_thumb_urls,
    strip_aged_out_auctions,
)
from scraper.filters import make_run_id, tomorrow_min_closing_date
from scraper.import_tracking import finalize_export_payload, stable_auction_key
from scraper.incremental import build_record_index, load_export
from scraper.incremental_materialize import materialize_incremental_export
from scraper.incremental_plan import build_work_plan
from scraper.main import enrich_auction, resolve_auction_listing
from scraper.models import AuctionRecord, AuctionsExport, ExtractionStatus
from scraper.pipeline_ledger import (
    load_ledger,
    mark_parse,
    pull_ledger,
    push_ledger,
    select_for_parse,
    write_ledger,
)
from scraper.promote_export import promote_export
from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, pull_raw_files
from scraper.refresh_and_deploy import _bootstrap_previous_production_from_live
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.safety_gates import SafetyGateConfig, run_safety_gates
from scraper.source_fallback import apply_missing_source_fallback
from scraper.telegram_reporter import send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_parse")


def _should_defer_parse_overlay(record: AuctionRecord) -> bool:
    """True when this parse must not replace previous production in materialize."""
    if record.status == ExtractionStatus.FAILED:
        return True
    errors = [str(e).lower() for e in (record.errors or [])]
    if any("pdf missing for parse_only" in err for err in errors):
        return True
    return False


def _parse_defer_reason(record: AuctionRecord) -> str:
    for err in record.errors or []:
        text = str(err)
        if "pdf missing for parse_only" in text.lower():
            return f"parse_repair_pending:{text[:160]}"
    if record.errors:
        return f"parse_repair_pending:{str(record.errors[0])[:160]}"
    return f"parse_repair_pending:status={record.status}"


def _phase(msg: str) -> None:
    """Visible CI progress even if logging handlers buffer oddly."""
    line = f"[pipeline_parse] {msg}"
    print(line, flush=True)
    logger.info(msg)


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
            logging.FileHandler(run_dir / "parse.log", encoding="utf-8"),
        ],
        force=True,
    )


def _push_auctions_json(local_json: Path) -> bool:
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None or not local_json.is_file():
        return False
    target = f"{cfg['username']}@{cfg['host']}"
    remote = f"{target}:{cfg['remote_dir']}/data/auctions.json"
    cmd = ["rsync", "-az", "-e", _ssh_cmd(cfg), str(local_json), remote]
    try:
        subprocess.run(cmd, check=True, timeout=180, capture_output=True, text=True)
        return True
    except Exception as exc:
        logger.warning("push auctions.json failed: %s", exc)
        return False


def _enrich_non_mstc_batch(source: str, auction_ids: set[str]) -> dict[str, AuctionRecord]:
    """One live scrape per source for all selected GeM / eAuction IDs."""
    if not auction_ids:
        return {}
    out: dict[str, AuctionRecord] = {}
    if source == "gem_forward":
        from scraper.gem_forward_client import GemForwardClient
        from scraper.gem_forward_scraper import scrape_gem_forward
        from scraper.adapters.gem_forward_adapter import adapt_gem_forward_auction

        client = GemForwardClient(transport="auto")
        auctions = scrape_gem_forward(client=client, enrich=True, include_auction_ids=auction_ids)
        for auction in auctions:
            aid = str(getattr(auction, "auction_id", None) or "")
            if aid in auction_ids:
                out[aid] = adapt_gem_forward_auction(auction)
        return out
    if source == "eauction":
        from scraper.eauction_scraper import scrape_eauction_tabs
        from scraper.adapters.eauction_adapter import adapt_eauction_record

        rows, _stats = scrape_eauction_tabs(
            tabs=["closingTodayTab", "closingWeekTab", "closingTwoWeekTab"],
            enrich_details=True,
            include_auction_ids=auction_ids,
        )
        for row in rows:
            rec = adapt_eauction_record(row)
            aid = str(rec.source_auction_id or rec.id)
            if aid in auction_ids:
                out[aid] = rec
        return out
    return out


def run_pipeline_parse(
    *,
    repo_root: Path = REPO_ROOT,
    max_parse: int | None = PIPELINE_PARSE_CAP_DEFAULT,
    max_docs_per_run: int = 200,
    min_count: int = 1000,
    sources: list[str] | None = None,
    force_min_closing_date: str | None = None,
    promote: bool = True,
    break_stale_lock: bool = True,
    skip_docs: bool = False,
) -> dict[str, Any]:
    sources = sources or ["mstc", "gem_forward", "eauction"]
    run_id = f"parse_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)

    lock_path = repo_root / "work" / "parse.lock"
    acquire_refresh_lock(lock_path=lock_path, run_id=run_id, stale_minutes=360, break_stale_lock=break_stale_lock)

    min_closing = force_min_closing_date or tomorrow_min_closing_date()
    production_json = Path(DEFAULT_JSON_OUT)
    public_dir = repo_root / "web" / "public"
    pdf_dir = Path(DEFAULT_PDF_DIR)
    docs_dir = Path(DEFAULT_DOCS_DIR)
    thumbs_dir = Path(DEFAULT_THUMBS_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    candidate_path = run_dir / "candidate_auctions.json"

    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "parse",
        "started_at": started,
        "min_closing_date": min_closing,
        "sources": sources,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="parse_started")

    warnings: list[str] = []
    try:
        _phase("bootstrap: pulling live auctions.json")
        _bootstrap_previous_production_from_live(
            production_json=production_json,
            base_url=SITE_BASE_URL or None,
            warnings=warnings,
        )
        _phase("bootstrap: pulling pipeline ledger")
        pull_ledger(local_path=ledger_path, timeout_sec=300)

        previous_export = load_export(production_json)
        if not previous_export or int(previous_export.get("count") or 0) <= 0:
            raise RuntimeError(
                "parse job requires previous production export "
                f"(missing/empty at {production_json}; warnings={warnings[:5]})"
            )

        ledger = load_ledger(ledger_path)
        selected = select_for_parse(ledger, limit=max_parse)
        payload["selected_count"] = len(selected)
        payload["ledger"] = ledger.status_counts()
        _phase(f"parse selection: {len(selected)} (ledger={ledger.status_counts()})")
        send_telegram_report(payload, event="parse_selection")

        mstc_selected = [i for i in selected if i.source == "mstc"]
        _phase(f"bootstrap: pulling {len(mstc_selected)} selected raw HTML files + pdfs/")
        pull_raw_files(
            [(i.source, i.source_auction_id) for i in mstc_selected],
            raw_dir=raw_dir,
            timeout_sec=300,
        )
        # Pull existing Hostinger media so parse can reuse caches and avoid re-downloads.
        bootstrap_production_assets(
            public_dir=public_dir,
            dirs=("pdfs", "docs", "thumbs"),
            timeout_sec=900,
        )

        _phase(f"discovery: starting sources={sources}")
        discovery_path = run_dir / "discovery_latest.json"
        run_discovery(
            sources=sources,
            out_path=discovery_path,
            min_closing_date=min_closing,
            allow_small_output=True,
        )
        discovery_data = json.loads(discovery_path.read_text(encoding="utf-8"))
        _phase(f"discovery: done count={discovery_data.get('count')}")
        plan = build_work_plan(discovery_data, previous_export)
        discovery_by_key = {
            stable_auction_key(a): a for a in (discovery_data.get("auctions") or [])
        }

        parsed_records: list[AuctionRecord] = []
        # Defer mark_parse(ok=True) until safety gates pass (ledger honesty).
        pending_parse_ok: list[tuple[str, bool]] = []
        stats: dict[str, Any] = {
            "html_parsed_from_disk": 0,
            "html_failures": 0,
            "pdf_failures": 0,
            "pdf_cache_hits": 0,
            "lots_parsed": 0,
            "pdf_failed_ids": [],
        }
        ok_count = fail_count = 0
        docs_remaining = 0 if skip_docs else max(0, int(max_docs_per_run))
        session = __import__("requests").Session()

        # Batch live enrich for non-MSTC once per source (never N full scrapes).
        non_mstc_by_source: dict[str, set[str]] = {}
        for item in selected:
            if item.source != "mstc":
                non_mstc_by_source.setdefault(item.source, set()).add(item.source_auction_id)
        non_mstc_records: dict[tuple[str, str], AuctionRecord] = {}
        gem_client = None
        for src, ids in non_mstc_by_source.items():
            _phase(f"live enrich batch: {src} ids={len(ids)}")
            batch = _enrich_non_mstc_batch(src, ids)
            for aid, rec in batch.items():
                non_mstc_records[(src, aid)] = rec
            if src == "gem_forward" and batch and not skip_docs and docs_remaining > 0:
                from scraper.gem_forward_client import GemForwardClient
                from scraper.gem_forward_documents import attach_gem_documents

                gem_client = GemForwardClient(transport="auto")
                gem_client.init_session()
                for aid, rec in list(batch.items()):
                    if docs_remaining <= 0:
                        break
                    try:
                        updated = attach_gem_documents(
                            rec,
                            client=gem_client,
                            docs_dir=docs_dir,
                            thumbs_dir=thumbs_dir,
                        )
                        non_mstc_records[(src, aid)] = updated
                        new_docs = sum(len(l.documents or []) for l in (updated.lots or []))
                        old_docs = sum(len(l.documents or []) for l in (rec.lots or []))
                        if new_docs > old_docs:
                            docs_remaining = max(0, docs_remaining - (new_docs - old_docs))
                    except Exception as exc:
                        logger.warning("GeM doc attach failed for %s: %s", aid, exc)

        for idx, item in enumerate(selected, start=1):
            try:
                if item.source == "mstc":
                    disc = discovery_by_key.get(item.stable_key)
                    if disc:
                        try:
                            base = AuctionRecord.model_validate(disc)
                        except Exception:
                            base = resolve_auction_listing(item.source_auction_id)[0]
                    else:
                        base = resolve_auction_listing(item.source_auction_id)[0]
                    base.source = "mstc"
                    record = enrich_auction(
                        base,
                        pdf_dir=pdf_dir,
                        skip_pdf=False,
                        stats=stats,
                        mode="parse_only",
                        raw_dir=raw_dir,
                    )
                    if record.lots and docs_remaining > 0 and not skip_docs:
                        record, docs_remaining = process_auction_documents(
                            record,
                            docs_dir=docs_dir,
                            thumbs_dir=thumbs_dir,
                            skip_docs=False,
                            max_docs_remaining=docs_remaining,
                            session=session,
                            stats=stats,
                        )
                else:
                    record = non_mstc_records.get((item.source, item.source_auction_id))
                    if record is None:
                        raise RuntimeError(f"could not enrich {item.stable_key}")

                if _should_defer_parse_overlay(record):
                    # Missing PDF / failed enrich must not replace prior production.
                    mark_parse(
                        ledger,
                        item.stable_key,
                        ok=False,
                        error=_parse_defer_reason(record),
                    )
                    fail_count += 1
                    continue

                ready = record.status != ExtractionStatus.FAILED
                pending_parse_ok.append((item.stable_key, ready))
                parsed_records.append(record)
                ok_count += 1
            except Exception as exc:
                logger.exception("parse failed for %s", item.stable_key)
                mark_parse(ledger, item.stable_key, ok=False, error=str(exc))
                fail_count += 1
            if idx % 10 == 0 or idx == len(selected):
                _phase(
                    f"parse progress {idx}/{len(selected)} ok={ok_count} "
                    f"failed={fail_count} docs_left={docs_remaining}"
                )

        # Persist individual failures only; successes wait for gates.
        write_ledger(ledger, ledger_path)

        parsed_export = AuctionsExport(
            generated_at=datetime.now(IST),
            count=len(parsed_records),
            auctions=parsed_records,
            stats=stats,
        ).model_dump(mode="json")

        # Selected → deep_parse. Unselected deep work: keep previous when present,
        # otherwise reuse discovery shallow so new listings are not dropped.
        previous_keys = set(build_record_index(previous_export))
        selected_keys = {i.stable_key for i in selected}
        adjusted_items = []
        for wp in plan.items:
            if wp.stable_key in selected_keys:
                adjusted_items.append(wp.model_copy(update={"action": "deep_parse"}))
            elif wp.action == "deep_parse":
                if wp.stable_key in previous_keys:
                    adjusted_items.append(wp.model_copy(update={"action": "reuse_previous"}))
                else:
                    adjusted_items.append(wp.model_copy(update={"action": "reuse_discovery"}))
            else:
                adjusted_items.append(wp)

        adjusted_plan = plan.model_copy(update={"items": adjusted_items})
        quarantine_data = load_quarantine(pull_remote=True)
        q_keys = active_quarantine_keys(quarantine_data, pull_remote=False)
        if q_keys:
            _phase(f"quarantine active: {len(q_keys)}")
        candidate = materialize_incremental_export(
            work_plan=adjusted_plan,
            previous_export=previous_export,
            parsed_export=parsed_export,
            discovery_export=discovery_data,
            allow_missing_deep_parse=True,
            min_closing_date=min_closing,
            quarantine_keys=q_keys,
        )
        hygiene_dropped: list[dict[str, Any]] = []
        quarantine_added = 0
        if q_keys:
            q_result = apply_quarantine_skips(candidate, q_keys, min_count=min_count)
            candidate = q_result.export
            warnings.extend(q_result.warnings)
        strip_result = strip_aged_out_auctions(candidate, min_closing_date=min_closing)
        candidate = strip_result.export
        hygiene_dropped.extend(strip_result.dropped)
        warnings.extend(strip_result.warnings)
        if strip_result.dropped:
            _phase(f"hygiene: stripped {len(strip_result.dropped)} aged-out")

        repair_result = repair_absolute_asset_paths(candidate)
        candidate = repair_result.export
        hygiene_repaired = list(repair_result.repaired)
        warnings.extend(repair_result.warnings)
        if repair_result.repaired:
            _phase(f"hygiene: repaired {len(repair_result.repaired)} absolute asset path(s)")

        # Recover still-future gem/eauction from previous when discovery wiped them.
        candidate, fallback_report = apply_missing_source_fallback(
            candidate,
            previous_export=previous_export,
            min_closing_date=min_closing,
            fallback_sources=["eauction", "gem_forward"],
        )
        payload["source_fallback"] = fallback_report
        if fallback_report.get("applied"):
            warnings.append(f"source fallback applied: {fallback_report.get('sources')}")
            _phase(f"source fallback applied: {fallback_report.get('sources')}")
            if q_keys:
                q_result = apply_quarantine_skips(candidate, q_keys, min_count=min_count)
                candidate = q_result.export
                warnings.extend(q_result.warnings)
            strip_after_fb = strip_aged_out_auctions(candidate, min_closing_date=min_closing)
            candidate = strip_after_fb.export
            hygiene_dropped.extend(strip_after_fb.dropped)
            warnings.extend(strip_after_fb.warnings)
            repair_after_fb = repair_absolute_asset_paths(candidate)
            candidate = repair_after_fb.export
            hygiene_repaired.extend(repair_after_fb.repaired)
            warnings.extend(repair_after_fb.warnings)

        candidate["stats"] = dict(candidate.get("stats") or {})
        candidate["stats"]["pipeline_parse"] = {
            "ok": ok_count,
            "failed": fail_count,
            "selected": len(selected),
        }
        candidate = finalize_export_payload(
            candidate,
            previous_export=previous_export,
            automation_ran_at=datetime.now(IST),
            run_id=run_id,
        )
        write_auctions_json(candidate_path, candidate)

        gate_config = SafetyGateConfig(
            min_count=min_count,
            min_closing_date=min_closing,
            eauction_warn_only=True,
            production_json=production_json,
            require_sources=("mstc",),
            warn_only_sources=("gem_forward", "eauction"),
        )

        def _run_gates():
            return run_safety_gates(
                candidate_path,
                config=gate_config,
                public_dir=public_dir,
            )

        poison_quarantine_keys: list[str] = []
        gates = _run_gates()

        # Tiered recovery: repair absolute paths → strip aged-out → quarantine residual poison.
        if not gates.passed:
            classified = classify_strict_errors(gates.errors)
            if classified.absolute_path:
                _phase("gates: absolute paths — repair + re-QA")
                repair2 = repair_absolute_asset_paths(candidate)
                candidate = repair2.export
                hygiene_repaired.extend(repair2.repaired)
                warnings.extend(repair2.warnings)
                write_auctions_json(candidate_path, candidate)
                gates = _run_gates()
                classified = classify_strict_errors(gates.errors)

            if not gates.passed and classified.aged_out:
                _phase("gates: aged-out — strip + re-QA")
                strip2 = strip_aged_out_auctions(candidate, min_closing_date=min_closing)
                candidate = strip2.export
                hygiene_dropped.extend(strip2.dropped)
                warnings.extend(strip2.warnings)
                write_auctions_json(candidate_path, candidate)
                gates = _run_gates()
                classified = classify_strict_errors(gates.errors)

            if not gates.passed and is_record_recoverable(classified):
                keys_to_q = extract_record_keys_from_errors(classified, export=candidate)
                if keys_to_q:
                    error_class = (
                        "absolute_path"
                        if classified.absolute_path
                        else ("aged_out" if classified.aged_out else "bad_asset_url")
                    )
                    _phase(f"auto-quarantine {len(keys_to_q)} · {error_class}")
                    add_quarantine_entries(
                        keys_to_q,
                        reason=f"auto_{error_class}",
                        source="drain_parse",
                        hours=DEFAULT_AUTO_HOURS,
                        data=quarantine_data,
                        push_remote=True,
                        error_class=error_class,
                        last_error=(classified.record_recoverable or classified.all_errors())[0],
                    )
                    quarantine_added = len(keys_to_q)
                    poison_quarantine_keys = keys_to_q
                    q_result = apply_quarantine_skips(
                        candidate, set(keys_to_q), min_count=min_count
                    )
                    candidate = q_result.export
                    warnings.extend(q_result.warnings)
                    write_auctions_json(candidate_path, candidate)
                    gates = _run_gates()
                    send_telegram_report(
                        {
                            **payload,
                            "quarantine_added": quarantine_added,
                            "quarantine_hours": DEFAULT_AUTO_HOURS,
                            "quarantine_error_class": error_class,
                            "hygiene_note": format_quarantine_telegram_note(
                                keys_to_q, error_class=error_class
                            ),
                        },
                        event="quarantine_added",
                    )

        payload["safety_gates"] = {
            "passed": gates.passed,
            "errors": gates.errors,
            "warnings": gates.warnings,
            "candidate_count": gates.candidate_count,
            "production_count": gates.production_count,
        }
        payload["hygiene"] = {
            "dropped_aged_out": len(hygiene_dropped),
            "dropped_ids": [d.get("id") for d in hygiene_dropped[:20]],
            "repaired_absolute_paths": len(hygiene_repaired),
            "quarantine_added": quarantine_added,
            "quarantined_keys": poison_quarantine_keys[:50],
        }
        warnings.extend(gates.warnings)
        if not gates.passed:
            classified = classify_strict_errors(gates.errors)
            fatal = classified.site_threatening or classified.all_errors()
            raise RuntimeError(f"safety gates failed: {fatal}")

        # Gates passed — mark successes done; poison-quarantined batch keys stay failed.
        poison_set = set(poison_quarantine_keys)
        for stable_key, ready in pending_parse_ok:
            if stable_key in poison_set:
                mark_parse(
                    ledger,
                    stable_key,
                    ok=False,
                    error=f"quarantined:{stable_key}",
                )
            else:
                mark_parse(ledger, stable_key, ok=True, deploy_ready=ready)
        write_ledger(ledger, ledger_path)

        # Scrub orphan local asset refs (incl. lot.documents) before media push / promote.
        removed = remove_missing_local_asset_links(candidate, public_dir=public_dir)
        if any(removed.values()):
            cand_stats = dict(candidate.get("stats") or {})
            cand_stats["missing_local_asset_links_removed"] = sum(removed.values())
            candidate["stats"] = cand_stats
            write_auctions_json(candidate_path, candidate)
            warnings.append(
                f"scrubbed missing local assets: pdfs={removed['pdfs']} "
                f"docs={removed['docs']} thumbs={removed['thumbs']}"
            )

        # Migrate legacy unsafe lot thumb dirs (4.0 → 4_0) and rewrite JSON URLs
        # before Hostinger media push — prevents rsync code 23 freezes.
        thumbs_dir = public_dir / "thumbs"
        migrate_stats = migrate_unsafe_thumb_dirs(thumbs_dir)
        url_stats = rewrite_unsafe_thumb_urls(candidate)
        if migrate_stats.get("renamed") or migrate_stats.get("merged") or url_stats.get("rewritten"):
            cand_stats = dict(candidate.get("stats") or {})
            cand_stats["thumb_lot_migrate"] = migrate_stats
            cand_stats["thumb_url_rewrite"] = url_stats
            candidate["stats"] = cand_stats
            write_auctions_json(candidate_path, candidate)
            warnings.append(
                "thumb lot migrate: "
                f"renamed={migrate_stats.get('renamed', 0)} "
                f"merged={migrate_stats.get('merged', 0)} "
                f"urls_rewritten={url_stats.get('rewritten', 0)}"
            )
            _phase(
                f"thumbs migrate renamed={migrate_stats.get('renamed', 0)} "
                f"merged={migrate_stats.get('merged', 0)} "
                f"urls={url_stats.get('rewritten', 0)}"
            )

        doc_stats = (stats.get("documents") or {}) if isinstance(stats, dict) else {}
        docs_downloaded = int(doc_stats.get("downloaded") or 0)
        needs_media = export_needs_media_push(
            candidate,
            public_dir=public_dir,
            documents_downloaded=docs_downloaded,
        )
        media_result = None
        if needs_media:
            _phase("media: pushing docs/thumbs/pdfs to Hostinger")
            media_result = push_public_media(public_dir=public_dir)
            payload["media_push"] = media_result.to_dict()
            if media_result.ok:
                warnings.append(
                    f"media push ok ({docs_downloaded} new docs this run)"
                    if docs_downloaded
                    else "media push ok"
                )
                now_iso = datetime.now(IST).isoformat()
                for stable_key, _ready in pending_parse_ok:
                    if stable_key in poison_set:
                        continue
                    item = ledger.by_key().get(stable_key)
                    if item is None:
                        continue
                    item.media_synced = True
                    item.media_synced_at = now_iso
                    item.deploy_ready = True
            else:
                msg = media_result.message or "media push failed"
                warnings.append(f"media push failed: {msg}")
                if media_push_required():
                    for stable_key, _ready in pending_parse_ok:
                        if stable_key in poison_set:
                            continue
                        mark_parse(
                            ledger,
                            stable_key,
                            ok=False,
                            error=f"media_push_failed:{msg[:120]}",
                        )
                        item = ledger.by_key().get(stable_key)
                        if item is not None:
                            item.media_synced = False
                            item.deploy_ready = False
                    write_ledger(ledger, ledger_path)
                    raise RuntimeError(
                        f"media push required but failed: {msg}; "
                        "set MEDIA_PUSH_REQUIRED=0 to scrub and promote without sync"
                    )
                # Escape hatch: scrub again and allow promote with pending_cache.
                remove_missing_local_asset_links(candidate, public_dir=public_dir)
                write_auctions_json(candidate_path, candidate)
            write_ledger(ledger, ledger_path)

        promoted = False
        if promote:
            promote_export(
                candidate=candidate_path,
                target=production_json,
                min_count=min_count,
                min_closing_date=min_closing,
                backup_dir=repo_root / "work" / "backups",
                require_sources=["mstc"],
                warn_missing_sources=["gem_forward", "eauction"],
                automation_ran_at=datetime.now(IST),
                run_id=run_id,
            )
            promoted = True
            # Public Hostinger surfaces update only via pipeline_deploy build:prod.
            # Do not rsync auctions.json alone (listing/HTML drift).

        push_ledger(local_path=ledger_path)

        notes = [
            format_dropped_telegram_note(hygiene_dropped),
            format_repair_telegram_note(hygiene_repaired),
            format_quarantine_telegram_note(
                poison_quarantine_keys,
                error_class="poison",
            ),
        ]
        drop_note = " · ".join(n for n in notes if n)
        payload.update(
            {
                "status": "success",
                "finished_at": datetime.now(IST).isoformat(),
                "parse_ok": ok_count,
                "parse_failed": fail_count,
                "promoted": promoted,
                "auctions": candidate.get("count"),
                "ledger": ledger.status_counts(),
                "warnings": warnings,
                "dropped_aged_out": len(hygiene_dropped),
                "repaired_absolute_paths": len(hygiene_repaired),
                "quarantined_keys": poison_quarantine_keys,
                "hygiene_note": drop_note,
                "quarantine_added": quarantine_added,
                "recoverable_parse_errors": (
                    len(hygiene_dropped) + len(hygiene_repaired) + quarantine_added
                ),
            }
        )
        (run_dir / "parse_report.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        send_telegram_report(payload, event="parse_done")
        return payload
    except Exception as exc:
        logger.exception("pipeline parse failed")
        payload["status"] = "failed"
        payload["errors"] = [str(exc)]
        payload["warnings"] = warnings
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="parse_failed")
        raise
    finally:
        release_refresh_lock(lock_path, run_id=run_id)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline job 2: parse raw assets")
    parser.add_argument(
        "--max-parse",
        type=int,
        default=PIPELINE_PARSE_CAP_DEFAULT,
        help="Max auctions to parse this run (default 100)",
    )
    parser.add_argument(
        "--max-docs-per-run",
        type=int,
        default=200,
        help="Shared MSTC document download budget for this parse run",
    )
    parser.add_argument("--skip-docs", action="store_true", help="Skip lot document/thumb downloads")
    parser.add_argument("--min-count", type=int, default=1000)
    parser.add_argument("--sources", default="mstc,gem_forward,eauction")
    parser.add_argument("--min-closing-date", default=None)
    parser.add_argument("--no-promote", action="store_true")
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_pipeline_parse(
        max_parse=args.max_parse,
        max_docs_per_run=args.max_docs_per_run,
        min_count=args.min_count,
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        force_min_closing_date=args.min_closing_date,
        promote=not args.no_promote,
        break_stale_lock=args.break_stale_lock,
        skip_docs=args.skip_docs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
