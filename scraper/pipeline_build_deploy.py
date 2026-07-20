"""Build/Deploy lane (v3): publish ONLY publishable auctions (Hostinger doc + lots)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import (
    DEFAULT_JSON_OUT,
    DEFAULT_PARSED_DIR,
    DEFAULT_PIPELINE_LEDGER,
    PARSER_CACHE_VERSION,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.export_guard import write_auctions_json
from scraper.export_hygiene import repair_absolute_asset_paths, strip_aged_out_auctions
from scraper.filters import make_run_id, resolve_min_closing
from scraper.import_tracking import stable_auction_key
from scraper.lane_resume import kick_if_needed, record_resume
from scraper.media_urls import absolutize_auction_media, absolutize_export_media
from scraper.object_store import media_key_from_url
from scraper.parse_cache import iter_local_parsed, load_parse_artifact, pull_parsed_tree
from scraper.pipeline_deploy import run_pipeline_deploy
from scraper.pipeline_ledger import (
    compute_publishable,
    count_publishable_future,
    load_ledger,
    mark_deploy,
    mark_parse,
    media_doc_path,
    media_doc_url,
    public_doc_url,
    pull_ledger,
    push_ledger,
    select_publishable,
    select_publishable_future,
    write_ledger,
)
from scraper.pipeline_markers import pull_pipeline_json
from scraper.pipeline_status import publish_pipeline_status, truth_for_telegram
from scraper.promote_export import promote_export
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_build_deploy")


def _phase(msg: str) -> None:
    print(f"[build_deploy] {msg}", flush=True)
    logger.info(msg)


def reconcile_parse_marks_from_artifacts(ledger: Any, parsed_root: Path) -> int:
    """Restore parse=done from on-disk artifacts when ledger marks were wiped.

    Concurrent VPS download pushes used to clobber GHA parse marks (last-writer-wins).
    Parsed JSON still lives under Hostinger/work parsed/; rebuild ledger from that.
    """
    healed = 0
    for item in list(ledger.items):
        if item.download != "done":
            continue
        if not media_doc_url(item) or not media_doc_path(item):
            continue
        if item.parse == "done" and int(item.lots_count or 0) > 0:
            continue
        path = parsed_root / item.source / f"{item.source_auction_id}.json"
        art = load_parse_artifact(path)
        if not art:
            continue
        rec = art.get("record")
        if not isinstance(rec, dict):
            continue
        lots = rec.get("lots") or []
        if not isinstance(lots, list) or not lots:
            continue
        rel = f"parsed/{item.source}/{item.source_auction_id}.json"
        mark_parse(
            ledger,
            item.stable_key,
            ok=True,
            lots_count=len(lots),
            parsed_path=rel,
            parser_version=str(art.get("parser_version") or PARSER_CACHE_VERSION),
        )
        healed += 1
    return healed


def _load_discovery_snapshots() -> dict[str, dict[str, Any]]:
    """stable_key → listing fields from discovery (never published alone)."""
    out: dict[str, dict[str, Any]] = {}
    for name in ("discovery_mstc_latest.json", "discovery_gem_latest.json", "discovery_latest.json"):
        data = pull_pipeline_json(name)
        if not data:
            continue
        for a in data.get("auctions") or []:
            if not isinstance(a, dict):
                continue
            key = stable_auction_key(a)
            out[key] = a
    return out


def materialize_publishable_only(
    *,
    ledger_items: list[Any],
    parsed_root: Path,
    discovery_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build export strictly from publishable ledger rows + parse cache."""
    records: list[dict[str, Any]] = []
    for item in ledger_items:
        if not compute_publishable(item):
            continue
        path = parsed_root / item.source / f"{item.source_auction_id}.json"
        if item.parsed_path:
            # parsed_path is like parsed/mstc/id.json
            alt = REPO_ROOT / "work" / item.parsed_path
            if alt.is_file():
                path = alt
            local = parsed_root / item.source / f"{item.source_auction_id}.json"
            if local.is_file():
                path = local
        art = load_parse_artifact(path)
        if not art:
            # try iter fallback
            for p in iter_local_parsed(parsed_root):
                if p.stem == str(item.source_auction_id) and item.source in str(p):
                    art = load_parse_artifact(p)
                    break
        if not art:
            continue
        rec = art.get("record")
        if not isinstance(rec, dict):
            continue
        lots = rec.get("lots") or []
        if not isinstance(lots, list) or not lots:
            continue
        # Require durable CDN doc on the record
        host_url = media_doc_url(item) or rec.get("object_doc_url") or rec.get("hostinger_doc_url")
        host_path = media_doc_path(item) or media_key_from_url(str(rec.get("pdf_url") or "")) or rec.get(
            "hostinger_doc_path"
        ) or rec.get("pdf_url")
        if not host_url or not host_path:
            continue

        disc = discovery_by_key.get(item.stable_key) or {}
        merged = dict(disc)
        merged.update(rec)
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
            "seller",
        ):
            if disc.get(fld) not in (None, ""):
                merged[fld] = disc[fld]
            elif getattr(item, fld, None) not in (None, ""):
                merged[fld] = getattr(item, fld)

        merged["source"] = item.source
        merged["source_auction_id"] = item.source_auction_id
        host_path_rel = str(host_path).lstrip("/")
        key = media_key_from_url(host_path_rel) or host_path_rel
        cdn = public_doc_url(key) if key.startswith(("pdfs/", "docs/")) else str(host_url)
        # Canonical public media: absolute CDN URL; keep relative key for ops.
        merged["hostinger_doc_path"] = key if key.startswith(("pdfs/", "docs/")) else host_path_rel
        merged["object_doc_url"] = cdn
        merged["hostinger_doc_url"] = cdn
        merged["pdf_url"] = cdn
        merged["source_pdf_url"] = item.portal_doc_url or merged.get("source_pdf_url")
        for key_docs in ("document_urls",):
            docs = merged.get(key_docs)
            if isinstance(docs, list):
                merged[key_docs] = [
                    (d.lstrip("/") if isinstance(d, str) else d) for d in docs
                ]
        merged["status"] = "complete"
        merged["enrichment_status"] = "parsed"
        meta = art.get("meta") or {}
        merged["pipeline"] = {
            "parsed_at": meta.get("parsed_at") or item.parsed_at,
            "doc_sha256": item.doc_sha256 or meta.get("pdf_sha256"),
            "parser_version": meta.get("parser_version") or item.parser_version,
            "object_doc_url": cdn,
            "hostinger_doc_url": cdn,
        }
        warnings = [w for w in (merged.get("warnings") or []) if "deep_enrichment" not in str(w)]
        merged["warnings"] = warnings
        absolutize_auction_media(merged)
        records.append(merged)

    records = [a for a in records if str(a.get("source") or "") != "eauction"]
    records.sort(key=lambda r: r.get("closing") or "")
    return {
        "generated_at": datetime.now(IST).isoformat(),
        "count": len(records),
        "auctions": records,
        "stats": {"publishable": len(records)},
        "schema_version": 3,
    }


def run_build_deploy(
    *,
    repo_root: Path = REPO_ROOT,
    deploy: bool = True,
    break_stale_lock: bool = True,
    allow_small_export: bool = False,
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
        pulled = pull_ledger(local_path=ledger_path)
        pull_parsed_tree(local_root=parsed_root)
        ledger = load_ledger(ledger_path)
        if not pulled and not ledger.items:
            raise RuntimeError(
                "ledger pull failed and local ledger is empty — refusing build-deploy"
            )
        discovery_by_key = _load_discovery_snapshots()
        # Heal parse marks wiped by concurrent download ledger pushes (artifacts remain).
        healed = reconcile_parse_marks_from_artifacts(ledger, parsed_root)
        if healed:
            write_ledger(ledger, ledger_path)
            push_ledger(local_path=ledger_path)
            _phase(f"reconciled parse marks from artifacts: {healed}")
        publishable = select_publishable(ledger)
        _phase(f"publishable={len(publishable)} ledger_total={len(ledger.items)}")

        export = materialize_publishable_only(
            ledger_items=publishable,
            parsed_root=parsed_root,
            discovery_by_key=discovery_by_key,
        )
        # Hard filter again
        cleaned = []
        for a in export.get("auctions") or []:
            if not (a.get("lots") or []):
                continue
            if not (a.get("object_doc_url") or a.get("hostinger_doc_url") or a.get("pdf_url")):
                continue
            cleaned.append(a)
        export["auctions"] = cleaned
        export["count"] = len(cleaned)
        min_closing_dt = resolve_min_closing()
        min_closing = min_closing_dt.isoformat()
        strip = strip_aged_out_auctions(
            export,
            min_closing_date=min_closing,
            # Cutover / growth: runway floor can age out >poison_threshold in one pass.
            allow_large_aged_out_strip=bool(allow_small_export),
        )
        export = strip.export
        repair = repair_absolute_asset_paths(export)
        export = repair.export
        absolutize_export_media(export)
        export["count"] = len(export.get("auctions") or [])
        _phase(
            f"export_ready={export['count']} "
            f"(stripped_aged={len(strip.dropped)} repaired_paths={len(repair.repaired)})"
        )

        # Media lives on CDN — no Hostinger media pull required for export correctness.
        _phase("media: CDN mode — skipping Hostinger asset pull")

        # Empty export: do not promote (would fail QA / wipe site). Soft noop for Telegram.
        if export["count"] == 0 and not allow_small_export:
            future_n = count_publishable_future(ledger, min_closing_date=min_closing)
            truth = publish_pipeline_status(
                ledger,
                lane="build_deploy",
                wake_reason="noop_empty_export",
                live_n=0,
                extra={"published": 0, "healed_parse_marks": healed},
            )
            send_lane_report(
                "build_deploy",
                "finished",
                {
                    "published": 0,
                    "live_on_site": 0,
                    "ready_for_site": future_n,
                    "aged_out": int(truth.get("aged_out_parsed") or 0),
                },
                noop=True,
            )
            payload = {
                "run_id": run_id,
                "published": 0,
                "status": "noop_empty_export",
                "publishable_future": future_n,
                "healed_parse_marks": healed,
            }
            (run_dir / "build_deploy_report.json").write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            _phase(f"noop: export_ready=0 publishable_future={future_n} healed={healed}")
            return payload

        candidate = run_dir / "candidate_auctions.json"
        write_auctions_json(candidate, export, allow_small_output=True)
        backup_dir = repo_root / "work" / "export_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Cutover: allow tiny/empty publishable sets
        if allow_small_export:
            min_count = 0
            req_sources: list[str] = []
        else:
            min_count = max(1, min(50, export["count"] or 1))
            req_sources = ["mstc"] if export["count"] >= 10 else []

        promote_export(
            candidate=candidate,
            target=production_json,
            min_count=min_count,
            min_closing_date=min_closing,
            backup_dir=backup_dir,
            require_sources=req_sources,
            warn_missing_sources=["gem_forward"],
            allow_small_output=True,
        )

        if deploy:
            os.environ["AI_ENRICHMENT_DISABLE"] = "1"
            # pipeline_deploy may enforce higher min_count — set env override
            if allow_small_export:
                os.environ["PIPELINE_ALLOW_SMALL_EXPORT"] = "1"
            run_pipeline_deploy(deploy=True, force=True, break_stale_lock=True)

        for a in export.get("auctions") or []:
            key = stable_auction_key(a)
            mark_deploy(ledger, key, ok=True)
        write_ledger(ledger, ledger_path)
        push_ledger(local_path=ledger_path)

        future_n = count_publishable_future(ledger, min_closing_date=min_closing)
        future_pending = sum(
            1
            for i in select_publishable_future(ledger, min_closing_date=min_closing)
            if i.deploy != "done"
        )
        # Self-resume when future publishable still not reflected as deploy=done
        kicked = False
        kick_reason = ""
        if future_pending > 0 and export["count"] > 0:
            # Avoid infinite loop on unmaterializable rows: only resume once per marker window
            prior = pull_pipeline_json("build_deploy_resume.json") or {}
            prior_pending = int(prior.get("future_pending") or -1)
            if prior_pending != future_pending:
                kicked, kick_reason = kick_if_needed(
                    "pipeline-build-deploy.yml",
                    reason="future_publishable_pending_deploy",
                    backlog=future_pending,
                    inputs={"allow_small_export": "true"},
                )
                if kicked:
                    record_resume(
                        "build_deploy",
                        {
                            "reason": kick_reason,
                            "future_pending": future_pending,
                            "published": export["count"],
                        },
                    )

        truth = publish_pipeline_status(
            ledger,
            lane="build_deploy",
            wake_reason=kick_reason or "complete",
            live_n=export["count"],
            extra={
                "published": export["count"],
                "stripped_aged": len(strip.dropped),
                "future_pending_deploy": future_pending,
                "self_resume": kicked,
            },
        )

        send_lane_report(
            "build_deploy",
            "finished",
            {
                "published": export["count"],
                "live_on_site": export["count"],
                "ready_for_site": future_n,
                "aged_out": int(truth.get("aged_out_parsed") or len(strip.dropped)),
            },
            noop=export["count"] == 0 and not allow_small_export,
        )
        payload = {
            "run_id": run_id,
            "published": export["count"],
            "allow_small_export": allow_small_export,
            "publishable_future": future_n,
            "future_pending_deploy": future_pending,
            "self_resume": kicked,
            "truth": truth_for_telegram(truth),
        }
        (run_dir / "build_deploy_report.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        _phase(
            f"done published={export['count']} future={future_n} "
            f"pending_deploy={future_pending} self_resume={kicked}"
        )
        return payload
    except Exception as exc:
        send_lane_report("build_deploy", "failed", {"error": str(exc)})
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build + deploy lane (v3 publishable-only)")
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument(
        "--allow-small-export",
        action="store_true",
        help="Cutover: allow publishing a small (or empty) ready-only set",
    )
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_build_deploy(
        deploy=not args.no_deploy,
        break_stale_lock=args.break_stale_lock,
        allow_small_export=args.allow_small_export,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
