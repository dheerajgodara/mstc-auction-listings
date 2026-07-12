from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
import traceback
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.asset_bootstrap import bootstrap_production_assets
from scraper.batch_manifest import BATCH_STATUS_FAILED
from scraper.batch_run import batch_run
from scraper.config import (
    DEFAULT_DOCS_DIR,
    DEFAULT_JSON_OUT,
    DEFAULT_PDF_DIR,
    DEFAULT_THUMBS_DIR,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.deploy import deploy as deploy_to_hostinger
from scraper.discovery import run_discovery
from scraper.export_guard import ExportGuardError
from scraper.filters import tomorrow_min_closing_date, make_run_id
from scraper.http_verify import verify_live_site
from scraper.import_tracking import finalize_export_payload
from scraper.incremental_materialize import materialize_incremental_export
from scraper.incremental_plan import build_work_plan, write_action_id_lists, write_work_plan
from scraper.incremental_queue import apply_queue_limit, finalize_queue_after_run
from scraper.merge_batches import merge_batches
from scraper.predeploy_verify import verify_predeploy_build
from scraper.promote_export import promote_export
from scraper.refresh_lock import (
    DEFAULT_LOCK_PATH,
    RefreshLockError,
    acquire_refresh_lock,
    release_refresh_lock,
)
from scraper.refresh_reports import (
    load_production_summary,
    update_latest_run,
    write_final_reports,
)
from scraper.notify import send_failure_notification
from scraper.safety_gates import SafetyGateConfig, run_safety_gates
from scraper.source_fallback import apply_missing_source_fallback, load_export, source_counts
from scraper.telegram_reporter import send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.refresh_and_deploy")

MAX_DISCOVERY_DROP_PCT = 0.40


def _subprocess_fail_summary(output: dict[str, Any], *, limit: int = 800) -> str:
    """Prefer FAIL lines from stdout (verify scripts print there); fall back to stderr."""
    stdout = str(output.get("stdout_tail") or "")
    stderr = str(output.get("stderr_tail") or "")
    fail_lines = [line.strip() for line in stdout.splitlines() if "FAIL" in line]
    if fail_lines:
        summary = "; ".join(fail_lines[:8])
        return summary[:limit]
    combined = (stderr or stdout).strip()
    return combined[-limit:] if combined else "(no output captured)"


class SubprocessStepError(RuntimeError):
    """Raised when a build/verify subprocess fails; carries captured output for reports."""

    def __init__(self, step: str, returncode: int, output: dict[str, Any]):
        self.step = step
        self.returncode = returncode
        self.output = output
        detail = _subprocess_fail_summary(output)
        super().__init__(f"{step} failed (exit {returncode}); {detail}")


def _repo_path(repo_root: Path, default_path: Path) -> Path:
    """Resolve historical absolute config defaults under the active repo root."""
    path = Path(default_path)
    if path.is_absolute():
        try:
            path = path.relative_to(REPO_ROOT)
        except ValueError:
            return path
    return repo_root / path


@dataclass
class RefreshConfig:
    sources: list[str] = field(default_factory=lambda: ["mstc", "gem_forward", "eauction"])
    max_docs_per_run: int = 2000
    min_count: int = 1000
    deploy: bool = False
    skip_build: bool = False
    skip_docs: bool = False
    force_min_closing_date: str | None = None
    resume_run_id: str | None = None
    notify_only_on_failure: bool = False
    lock_timeout_minutes: int = 10
    break_stale_lock: bool = False
    allow_large_drop: bool = False
    allow_failed_batches: bool = False
    eauction_warn_only: bool = False
    fallback_sources: list[str] = field(default_factory=lambda: ["mstc", "gem_forward", "eauction"])
    full_reconcile: bool = False
    max_deep_scrape_per_run: int = 200
    repo_root: Path = REPO_ROOT
    lock_path: Path = DEFAULT_LOCK_PATH


@dataclass
class RefreshResult:
    status: str
    run_id: str
    run_dir: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_paths: dict[str, str] = field(default_factory=dict)


def _setup_run_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "refresh.log"
    root = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file) for h in root.handlers):
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(handler)


def _run_subprocess(cmd: list[str], *, cwd: Path, step: str) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    duration = round(time.monotonic() - started, 2)
    output: dict[str, Any] = {
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "duration_sec": duration,
    }
    if result.returncode != 0:
        output["stderr_tail"] = (result.stderr or "")[-2000:]
        output["stdout_tail"] = (result.stdout or "")[-2000:]
        raise SubprocessStepError(step, result.returncode, output)
    return output


def _assert_discovery_completeness(
    *,
    sources: list[str],
    discovery_data: dict[str, Any],
    previous_export: dict[str, Any] | None,
    allow_large_drop: bool,
) -> None:
    """Abort before work-plan when post-fallback discovery would wipe MSTC / crash counts."""
    previous_counts = source_counts(previous_export)
    current_counts = source_counts(discovery_data)
    previous_total = int((previous_export or {}).get("count") or sum(previous_counts.values()) or 0)
    current_total = int(discovery_data.get("count") or sum(current_counts.values()) or 0)

    if "mstc" in sources:
        prev_mstc = int(previous_counts.get("mstc") or 0)
        cur_mstc = int(current_counts.get("mstc") or 0)
        if prev_mstc > 0 and cur_mstc == 0:
            raise RuntimeError(
                f"discovery completeness gate failed: MSTC count is 0 after source fallback "
                f"(previous MSTC={prev_mstc}); refusing to mark MSTC listings removed"
            )

    if (
        not allow_large_drop
        and previous_total > 0
        and current_total < previous_total * (1.0 - MAX_DISCOVERY_DROP_PCT)
    ):
        drop_pct = 100.0 * (previous_total - current_total) / previous_total
        raise RuntimeError(
            f"discovery completeness gate failed: total count dropped {drop_pct:.0f}% "
            f"({previous_total} -> {current_total}); refusing work plan"
        )


def _prepare_run_dirs(config: RefreshConfig) -> tuple[str, Path, Path, Path, Path, Path]:
    if config.resume_run_id:
        run_id = config.resume_run_id
        run_dir = config.repo_root / "work" / "runs" / run_id
        if not run_dir.is_dir():
            raise FileNotFoundError(f"Resume run dir not found: {run_dir}")
    else:
        run_id = make_run_id()
        run_dir = config.repo_root / "work" / "runs" / run_id
        for sub in ("batches", "logs", "reports"):
            (run_dir / sub).mkdir(parents=True, exist_ok=True)
    batches_dir = run_dir / "batches"
    logs_dir = run_dir / "logs"
    reports_dir = run_dir / "reports"
    candidate_path = run_dir / "future_full_auctions.json"
    return run_id, run_dir, batches_dir, logs_dir, reports_dir, candidate_path


def _snapshot_production_backup(
    *,
    production_json: Path,
    run_dir: Path,
    backup_dir: Path,
) -> Path | None:
    if not production_json.is_file():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"auctions_{stamp}.json"
    shutil.copy2(production_json, path)
    run_copy = run_dir / "previous_production.json"
    shutil.copy2(production_json, run_copy)
    meta = {
        "previous_production_backup_path": str(path),
        "previous_production_run_copy": str(run_copy),
        "previous_production_summary": load_production_summary(production_json),
        "captured_at": datetime.now(IST).isoformat(),
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def _write_candidate_payload(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_to_payload(export: Any, candidate_path: Path) -> dict[str, Any]:
    loaded = load_export(candidate_path)
    if loaded is not None:
        return loaded
    if hasattr(export, "model_dump"):
        return export.model_dump(mode="json")
    if isinstance(export, dict):
        return dict(export)
    raise RuntimeError("merge did not write candidate and export object is not serializable")


def _export_count(path: Path) -> int:
    data = load_export(path)
    if not data:
        return 0
    return int(data.get("count", len(data.get("auctions") or [])) or 0)


def _classify_failed_batches(manifest_data: dict[str, Any]) -> dict[str, list[str]]:
    failed_mstc: list[str] = []
    failed_non_mstc: list[str] = []
    for batch in manifest_data.get("batches", []) or []:
        if batch.get("status") != BATCH_STATUS_FAILED:
            continue
        batch_id = str(batch.get("batch_id") or "unknown")
        if batch.get("source") == "mstc":
            failed_mstc.append(batch_id)
        else:
            failed_non_mstc.append(batch_id)
    return {"mstc": failed_mstc, "non_mstc": failed_non_mstc, "all": failed_mstc + failed_non_mstc}


def _parse_auctions_data_js(text: str) -> dict[str, Any] | None:
    match = re.search(r"__AUCTIONS_EXPORT__\s*=\s*(\{.*\});?\s*$", text, re.S)
    if not match:
        return None
    return json.loads(match.group(1))


def _bootstrap_base_urls(base_url: str | None) -> list[str]:
    candidates: list[str] = []
    for raw in [
        os.environ.get("SITE_BASE_URL"),
        base_url,
        "https://scrapauctionindia.com/auctions",
    ]:
        value = (raw or "").strip().rstrip("/")
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def _read_remote_production_bundle_via_ssh() -> str:
    host = (os.environ.get("HOSTINGER_HOST") or "").strip()
    port = (os.environ.get("HOSTINGER_PORT") or "22").strip()
    username = (os.environ.get("HOSTINGER_USERNAME") or "").strip()
    key_path = os.path.expanduser((os.environ.get("HOSTINGER_SSH_KEY") or "").strip())
    remote_dir = (os.environ.get("HOSTINGER_REMOTE_DIR") or "").strip()
    if not all([host, username, key_path, remote_dir]):
        raise RuntimeError("Hostinger SSH bootstrap env is incomplete")

    remote_file = f"{remote_dir.rstrip('/')}/data/auctions-data.js"
    cmd = [
        "ssh",
        "-i",
        key_path,
        "-p",
        port,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        f"{username}@{host}",
        f"cat {shlex.quote(remote_file)}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ssh bootstrap failed").strip())
    return result.stdout


def _bootstrap_previous_production_from_live(
    *,
    production_json: Path,
    base_url: str | None,
    warnings: list[str],
) -> bool:
    if _export_count(production_json) > 0:
        return False
    base_urls = _bootstrap_base_urls(base_url)
    if not base_urls:
        warnings.append("no local production export and SITE_BASE_URL unavailable for bootstrap")
        return False

    data: dict[str, Any] | None = None
    for clean_base in base_urls:
        url = f"{clean_base}/data/auctions-data.js?v=bootstrap-{int(time.time())}"
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "ScrapAuctionIndiaRefresh/1.0 (+https://scrapauctionindia.com/auctions)",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=240) as resp:
                text = resp.read().decode("utf-8")
            data = _parse_auctions_data_js(text)
            if data is not None:
                break
            warnings.append(f"could not bootstrap previous production: live data bundle parse failed at {clean_base}")
        except Exception as exc:
            warnings.append(f"could not bootstrap previous production from {clean_base}: {exc}")
    if data is None:
        try:
            text = _read_remote_production_bundle_via_ssh()
            data = _parse_auctions_data_js(text)
            if data is None:
                warnings.append("could not bootstrap previous production: SSH data bundle parse failed")
                return False
            warnings.append("HTTP bootstrap unavailable; used Hostinger SSH production bundle")
        except Exception as exc:
            warnings.append(f"could not bootstrap previous production via Hostinger SSH: {exc}")
            return False

    count = int(data.get("count", len(data.get("auctions") or [])) or 0)
    if count <= 0:
        warnings.append("could not bootstrap previous production: live export was empty")
        return False

    production_json.parent.mkdir(parents=True, exist_ok=True)
    production_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    warnings.append(f"bootstrapped previous production from live site ({count} auctions)")
    return True


def run_refresh_and_deploy(config: RefreshConfig) -> RefreshResult:
    run_id, run_dir, batches_dir, logs_dir, reports_dir, candidate_path = _prepare_run_dirs(config)
    _setup_run_logging(logs_dir)

    min_closing_date = config.force_min_closing_date or tomorrow_min_closing_date()
    production_json = _repo_path(config.repo_root, DEFAULT_JSON_OUT)
    web_dir = config.repo_root / "web"
    out_dir = web_dir / "out"
    backup_dir = config.repo_root / "work" / "backups"

    started_at = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "started_at": started_at,
        "min_closing_date": min_closing_date,
        "sources": config.sources,
        "deploy_requested": config.deploy,
        "max_deep_scrape_per_run": config.max_deep_scrape_per_run,
        "mode": "full_reconcile" if config.full_reconcile else "incremental_queue",
        "site_base_url": SITE_BASE_URL,
        "github_run_url": (
            f"{os.environ.get('GITHUB_SERVER_URL')}/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/"
            f"{os.environ.get('GITHUB_RUN_ID')}"
            if os.environ.get("GITHUB_SERVER_URL")
            and os.environ.get("GITHUB_REPOSITORY")
            and os.environ.get("GITHUB_RUN_ID")
            else None
        ),
        "warnings": [],
        "errors": [],
    }
    send_telegram_report(payload, event="started")

    errors: list[str] = []
    warnings: list[str] = []
    promoted = False
    backup_path: Path | None = None
    previous_backup: Path | None = None

    lock_acquired = False
    try:
        acquire_refresh_lock(
            lock_path=config.repo_root / config.lock_path,
            run_id=run_id,
            stale_minutes=config.lock_timeout_minutes,
            break_stale_lock=config.break_stale_lock,
        )
        lock_acquired = True

        bootstrapped = _bootstrap_previous_production_from_live(
            production_json=production_json,
            base_url=SITE_BASE_URL or None,
            warnings=warnings,
        )
        payload["previous_production_bootstrap"] = {
            "attempted": bootstrapped or _export_count(production_json) == 0,
            "bootstrapped": bootstrapped,
            "production_count": _export_count(production_json),
        }

        previous_backup = _snapshot_production_backup(
            production_json=production_json,
            run_dir=run_dir,
            backup_dir=backup_dir,
        )
        payload["previous_production_backup_path"] = str(previous_backup) if previous_backup else None
        payload["previous_production_summary"] = load_production_summary(production_json)
        previous_export = load_export(production_json)

        work_plan_path: Path | None = None
        full_work_plan_path: Path | None = None
        queue_path = config.repo_root / "work" / "incremental_queue.json"
        selected_keys: set[str] = set()
        parsed_deep_path = run_dir / "parsed_deep_auctions.json"
        if not config.full_reconcile:
            if not previous_export or int(previous_export.get("count", 0) or 0) <= 0:
                raise RuntimeError(
                    "incremental refresh requires previous production data; "
                    "bootstrap failed and full scrape is disabled"
                )

            discovery_started = time.monotonic()
            discovery_path = run_dir / "discovery_latest.json"
            discovery_export = run_discovery(
                sources=config.sources,
                out_path=discovery_path,
                min_closing_date=min_closing_date,
                allow_small_output=True,
            )
            discovery_data = _export_to_payload(discovery_export, discovery_path)
            discovery_data, discovery_fallback_report = apply_missing_source_fallback(
                discovery_data,
                previous_export=previous_export,
                min_closing_date=min_closing_date,
                fallback_sources=config.fallback_sources,
            )
            if discovery_fallback_report.get("applied"):
                _write_candidate_payload(discovery_path, discovery_data)
                warnings.append(f"discovery source fallback applied: {discovery_fallback_report.get('sources')}")
            payload["discovery"] = {
                "duration_sec": round(time.monotonic() - discovery_started, 2),
                "raw_count": discovery_export.count,
                "raw_by_source": discovery_export.stats.get("by_source"),
                "count": int(discovery_data.get("count", discovery_export.count)),
                "by_source": discovery_data.get("stats", {}).get("by_source") or discovery_export.stats.get("by_source"),
                "source_stats": discovery_data.get("stats", {}).get("source_stats") or discovery_export.stats.get("source_stats"),
                "source_fallback": discovery_fallback_report,
            }
            _assert_discovery_completeness(
                sources=config.sources,
                discovery_data=discovery_data,
                previous_export=previous_export,
                allow_large_drop=config.allow_large_drop,
            )

            plan_started = time.monotonic()
            full_work_plan = build_work_plan(discovery_data, previous_export)
            full_work_plan_path = run_dir / "incremental_work_plan.full.json"
            write_work_plan(full_work_plan_path, full_work_plan)
            work_plan, queue_state = apply_queue_limit(
                full_work_plan,
                queue_path=queue_path,
                max_deep_scrape_per_run=config.max_deep_scrape_per_run,
                previous_export=previous_export,
                public_dir=config.repo_root / "web" / "public",
            )
            selected_keys = set(queue_state.selected_keys)
            work_plan_path = run_dir / "incremental_work_plan.selected.json"
            write_work_plan(work_plan_path, work_plan)
            write_action_id_lists(run_dir / "incremental_ids", work_plan)
            payload["incremental_work_plan"] = {
                "duration_sec": round(time.monotonic() - plan_started, 2),
                "full_path": str(full_work_plan_path),
                "path": str(work_plan_path),
                "full_counts": full_work_plan.counts,
                "full_action_counts": full_work_plan.action_counts,
                "selected_counts": work_plan.counts,
                "selected_action_counts": work_plan.action_counts,
                "selected_by_source": work_plan.by_source,
                "queue": queue_state.model_dump(mode="json"),
            }
            send_telegram_report(payload, event="comparison_done")

        # 1. Batch scrape
        scrape_started = time.monotonic()
        manifest = batch_run(
            sources=config.sources,
            batch_dir=batches_dir,
            pdf_dir=_repo_path(config.repo_root, DEFAULT_PDF_DIR),
            docs_dir=_repo_path(config.repo_root, DEFAULT_DOCS_DIR),
            thumbs_dir=_repo_path(config.repo_root, DEFAULT_THUMBS_DIR),
            min_closing_date=min_closing_date,
            max_docs_per_run=config.max_docs_per_run,
            resume=bool(config.resume_run_id),
            force=False,
            skip_docs=config.skip_docs,
            work_plan_path=work_plan_path,
        )
        failed_batch_groups = _classify_failed_batches(manifest.data)
        failed_batches = failed_batch_groups["all"]
        payload["batch_scrape"] = {
            "duration_sec": round(time.monotonic() - scrape_started, 2),
            "manifest_summary": manifest.summary(),
            "failed_batches": failed_batches,
            "failed_mstc_batches": failed_batch_groups["mstc"],
            "failed_non_mstc_batches": failed_batch_groups["non_mstc"],
            "docs_budget_remaining": manifest.data.get("docs_budget_remaining"),
        }
        send_telegram_report(payload, event="deep_scrape_done")
        if failed_batch_groups["mstc"] and not config.allow_failed_batches:
            raise RuntimeError(f"MSTC batch scrape had failures: {', '.join(failed_batch_groups['mstc'])}")
        if failed_batch_groups["non_mstc"]:
            warnings.append(
                "non-MSTC batch scrape failed; continuing with previous/discovery fallback: "
                + ", ".join(failed_batch_groups["non_mstc"])
            )

        # 2. Merge parsed/deep records
        merge_started = time.monotonic()
        export = merge_batches(
            batch_dir=batches_dir,
            out_path=parsed_deep_path if work_plan_path else candidate_path,
            min_closing_date=min_closing_date,
        )
        payload["merge"] = {
            "duration_sec": round(time.monotonic() - merge_started, 2),
            "count": export.count,
            "total_lots": export.stats.get("total_lots_in_export"),
            "by_source": export.stats.get("by_source"),
            "duplicates_removed": export.stats.get("duplicates_removed"),
        }
        payload["total_auctions"] = export.count
        payload["total_lots"] = export.stats.get("total_lots_in_export")
        payload["by_source"] = export.stats.get("by_source")
        doc_stats = export.stats.get("documents") or {}
        failed_by_reason = doc_stats.get("failed_by_reason") or {}
        payload["document_recovery"] = {
            "failed_total": int(doc_stats.get("failed", 0) or 0),
            "too_small": int(failed_by_reason.get("too_small", 0) or 0),
            "failed_by_reason": failed_by_reason,
            "failed_by_doc_type": doc_stats.get("failed_by_doc_type") or {},
        }

        if work_plan_path:
            materialize_started = time.monotonic()
            parsed_deep_data = _export_to_payload(export, parsed_deep_path)
            queue_state_after = finalize_queue_after_run(
                queue_path=queue_path,
                selected_keys=selected_keys,
                parsed_export=parsed_deep_data,
                max_deep_scrape_per_run=config.max_deep_scrape_per_run,
                previous_export=previous_export,
            )
            candidate_data = materialize_incremental_export(
                work_plan=work_plan,
                previous_export=previous_export,
                parsed_export=parsed_deep_data,
                discovery_export=discovery_data,
                allow_missing_deep_parse=True,
            )
            candidate_data.setdefault("stats", {})["incremental_queue_state"] = queue_state_after.model_dump(mode="json")
            _write_candidate_payload(candidate_path, candidate_data)
            payload["incremental_materialize"] = {
                "duration_sec": round(time.monotonic() - materialize_started, 2),
                **(candidate_data.get("stats", {}).get("incremental_materialize") or {}),
            }
            payload["incremental_queue"] = queue_state_after.model_dump(mode="json")
        else:
            candidate_data = _export_to_payload(export, candidate_path)

        # 2b. Fallback and finalization before gates.
        #
        # Safety gates validate import metadata, so candidate metadata must be
        # stamped before gates run. Also, a source-wide zero result for a flaky
        # source such as eAuction should not erase still-future production rows.
        candidate_data, fallback_report = apply_missing_source_fallback(
            candidate_data,
            previous_export=previous_export,
            min_closing_date=min_closing_date,
            fallback_sources=config.fallback_sources,
        )
        payload["source_fallback"] = fallback_report
        if fallback_report.get("applied"):
            warnings.append(f"source fallback applied: {fallback_report.get('sources')}")

        candidate_data = finalize_export_payload(
            candidate_data,
            previous_export=previous_export,
            automation_ran_at=datetime.now(IST),
            run_id=run_id,
            history_path=None,
            status="candidate",
        )
        _write_candidate_payload(candidate_path, candidate_data)

        payload["total_auctions"] = int(candidate_data.get("count", 0))
        payload["total_lots"] = candidate_data.get("stats", {}).get("total_lots_in_export")
        payload["by_source"] = candidate_data.get("stats", {}).get("by_source") or {
            source: meta.get("count", 0)
            for source, meta in (candidate_data.get("sources") or {}).items()
        }
        payload["candidate_finalization"] = {
            "automation_ran_at": candidate_data.get("automation_ran_at"),
            "run_id": candidate_data.get("run_id"),
            "imported_at_count": sum(
                1
                for auction in candidate_data.get("auctions", [])
                if auction.get("imported_at") or auction.get("first_seen_at")
            ),
        }

        # 3-4. QA + safety gates
        gate_config = SafetyGateConfig(
            min_count=config.min_count,
            min_closing_date=min_closing_date,
            allow_large_drop=config.allow_large_drop,
            allow_failed_batches=config.allow_failed_batches,
            eauction_warn_only=config.eauction_warn_only,
            production_json=production_json,
        )
        gates = run_safety_gates(
            candidate_path,
            config=gate_config,
            batch_dir=batches_dir,
            public_dir=config.repo_root / "web" / "public",
        )
        payload["qa"] = {
            "passed": gates.qa_report.get("passed"),
            "earliest_closing": gates.qa_report.get("earliest_closing"),
        }
        payload["safety_gates"] = {
            "passed": gates.passed,
            "errors": gates.errors,
            "warnings": gates.warnings,
            "candidate_count": gates.candidate_count,
            "production_count": gates.production_count,
        }
        warnings.extend(gates.warnings)
        if not gates.passed:
            errors.extend(gates.errors)
            raise RuntimeError("safety gates failed")

        # 5. Promote
        try:
            backup_path = promote_export(
                candidate=candidate_path,
                target=production_json,
                min_count=config.min_count,
                min_closing_date=min_closing_date,
                backup_dir=backup_dir,
                require_sources=["mstc"] if config.eauction_warn_only else ["mstc", "eauction"],
                warn_missing_sources=["gem_forward"],
                automation_ran_at=datetime.now(IST),
                run_id=run_id,
            )
            promoted = True
            payload["promotion"] = {
                "promoted": True,
                "backup_path": str(backup_path) if backup_path else None,
            }
            payload["rollback_backup_path"] = str(backup_path) if backup_path else None
        except ExportGuardError as exc:
            errors.append(str(exc))
            raise

        # 6. Bootstrap production media, then build (finalize_public_export runs inside build:prod)
        if not config.skip_build:
            public_dir = config.repo_root / "web" / "public"
            asset_boot = bootstrap_production_assets(public_dir=public_dir)
            payload["asset_bootstrap"] = asset_boot.to_dict()
            warnings.extend(asset_boot.warnings)
            if asset_boot.attempted and not asset_boot.ok:
                warnings.append(f"asset bootstrap weak: {asset_boot.message}")
            elif asset_boot.ok:
                warnings.append(asset_boot.message)

            build_started = time.monotonic()
            try:
                _run_subprocess(["pnpm", "run", "build:prod"], cwd=web_dir, step="build:prod")
                verify_out = _run_subprocess(["pnpm", "run", "verify-build"], cwd=web_dir, step="verify-build")
                payload["build"] = {
                    "duration_sec": round(time.monotonic() - build_started, 2),
                    "verify_build": verify_out,
                }
            except SubprocessStepError as exc:
                payload["build"] = {
                    "duration_sec": round(time.monotonic() - build_started, 2),
                    "failed_step": exc.step,
                    "returncode": exc.returncode,
                    "stderr_tail": exc.output.get("stderr_tail"),
                    "stdout_tail": exc.output.get("stdout_tail"),
                    "output": exc.output,
                }
                raise
        else:
            payload["build"] = {"skipped": True}

        # 7. Pre-deploy verify
        if config.deploy:
            predeploy = verify_predeploy_build(
                out_dir=out_dir,
                min_count=config.min_count,
                min_closing_date=min_closing_date,
                require_sources=["mstc"] if config.eauction_warn_only else ["mstc", "eauction"],
                warn_only_sources=["gem_forward"],
            )
            payload["predeploy"] = {
                "passed": predeploy.passed,
                "count": predeploy.count,
                "by_source": predeploy.by_source,
                "pdf_count": predeploy.pdf_count,
                "docs_count": predeploy.docs_count,
                "thumbs_count": predeploy.thumbs_count,
                "errors": predeploy.errors,
                "warnings": predeploy.warnings,
            }
            warnings.extend(predeploy.warnings)
            if not predeploy.passed:
                errors.extend(predeploy.errors)
                raise RuntimeError("pre-deploy verification failed")

            # 8. Deploy
            deploy_started = time.monotonic()
            deploy_to_hostinger(build_dir=out_dir)
            payload["deploy"] = {
                "deployed": True,
                "duration_sec": round(time.monotonic() - deploy_started, 2),
            }

            # 9. HTTP verify
            http_result = verify_live_site(
                base_url=SITE_BASE_URL or None,
                expected_count=int(candidate_data.get("count", export.count)),
                candidate_json=candidate_path,
                output_assets_dir=out_dir,
            )
            payload["http_verify"] = {
                "passed": http_result.passed,
                "index_status": http_result.index_status,
                "json_status": http_result.json_status,
                "data_js_status": http_result.data_js_status,
                "pdf_status": http_result.pdf_status,
                "thumb_status": http_result.thumb_status,
                "live_count_hint": http_result.live_count_hint,
                "checked_urls": http_result.checked_urls,
                "errors": http_result.errors,
                "warnings": http_result.warnings,
            }
            warnings.extend(http_result.warnings)
            if not http_result.passed:
                errors.extend(http_result.errors)
                raise RuntimeError("post-deploy HTTP verification failed")
        else:
            payload["deploy"] = {"deployed": False, "skipped": True}
            payload["http_verify"] = {"skipped": True}

        payload["status"] = "success"
        payload["finished_at"] = datetime.now(IST).isoformat()
        payload["warnings"] = warnings
        payload["errors"] = errors

        md_path, json_path = write_final_reports(reports_dir=reports_dir, payload=payload)
        update_latest_run(
            runs_root=config.repo_root / "work" / "runs",
            payload=payload,
            success=True,
        )
        send_telegram_report(payload, event="success")
        return RefreshResult(
            status="success",
            run_id=run_id,
            run_dir=run_dir,
            warnings=warnings,
            report_paths={"md": str(md_path), "json": str(json_path)},
        )

    except Exception as exc:
        logger.exception("refresh_and_deploy failed: %s", exc)
        if isinstance(exc, SubprocessStepError):
            errors.append(str(exc))
            payload.setdefault("build", {})
            if not payload.get("build"):
                payload["build"] = {
                    "failed_step": exc.step,
                    "returncode": exc.returncode,
                    "stderr_tail": exc.output.get("stderr_tail"),
                    "stdout_tail": exc.output.get("stdout_tail"),
                    "output": exc.output,
                }
        else:
            errors.append(str(exc))
        payload["status"] = "failed"
        payload["finished_at"] = datetime.now(IST).isoformat()
        payload["errors"] = errors
        payload["warnings"] = warnings
        payload["promotion"] = {"promoted": promoted, "backup_path": str(backup_path) if backup_path else None}
        if not config.deploy:
            payload["deploy"] = {"deployed": False, "skipped": True}

        reports_dir.mkdir(parents=True, exist_ok=True)
        md_path, json_path = write_final_reports(reports_dir=reports_dir, payload=payload)
        update_latest_run(
            runs_root=config.repo_root / "work" / "runs",
            payload=payload,
            success=False,
        )
        send_telegram_report(payload, event="failed")
        return RefreshResult(
            status="failed",
            run_id=run_id,
            run_dir=run_dir,
            errors=errors,
            warnings=warnings,
            report_paths={"md": str(md_path), "json": str(json_path)},
        )
    finally:
        if lock_acquired:
            release_refresh_lock(config.repo_root / config.lock_path, run_id=run_id)


def build_parser_for_tests() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Full refresh pipeline: scrape, QA, promote, build, deploy")
    parser.add_argument("--sources", default="mstc,gem_forward,eauction")
    parser.add_argument("--max-docs-per-run", type=int, default=2000)
    parser.add_argument("--max-deep-scrape", type=int, default=200)
    parser.add_argument("--min-count", type=int, default=1000)
    parser.add_argument("--deploy", action="store_true", help="Deploy to Hostinger after successful build")
    parser.add_argument("--no-deploy", action="store_true", help="Do not deploy (default)")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--force-min-closing-date", type=str, default=None)
    parser.add_argument("--resume-run", dest="resume_run", default=None)
    parser.add_argument("--notify-only-on-failure", action="store_true")
    parser.add_argument("--lock-timeout-minutes", type=int, default=10)
    parser.add_argument("--break-stale-lock", action="store_true")
    parser.add_argument("--allow-large-drop", action="store_true")
    parser.add_argument("--allow-failed-batches", action="store_true")
    parser.add_argument("--warn-missing-eauction", action="store_true")
    parser.add_argument(
        "--full-reconcile",
        action="store_true",
        help="Manual-only full deep scrape. Scheduled production runs should omit this.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser_for_tests()
    args = parser.parse_args(argv)

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    deploy = args.deploy and not args.no_deploy

    config = RefreshConfig(
        sources=sources,
        max_docs_per_run=args.max_docs_per_run,
        min_count=args.min_count,
        deploy=deploy,
        skip_build=args.skip_build,
        skip_docs=args.skip_docs,
        force_min_closing_date=args.force_min_closing_date,
        resume_run_id=args.resume_run,
        notify_only_on_failure=args.notify_only_on_failure,
        lock_timeout_minutes=args.lock_timeout_minutes,
        break_stale_lock=args.break_stale_lock,
        allow_large_drop=args.allow_large_drop,
        allow_failed_batches=args.allow_failed_batches,
        eauction_warn_only=args.warn_missing_eauction,
        full_reconcile=args.full_reconcile,
        max_deep_scrape_per_run=args.max_deep_scrape,
    )

    try:
        result = run_refresh_and_deploy(config)
    except RefreshLockError as exc:
        logger.error("%s", exc)
        return 3

    if result.status == "success":
        logger.info("Refresh completed successfully: %s", result.run_id)
        return 0
    logger.error("Refresh failed: %s", result.errors)
    if config.notify_only_on_failure or os.environ.get("NOTIFY_WEBHOOK_URL"):
        send_failure_notification(
            summary=f"Refresh run {result.run_id} failed: {'; '.join(result.errors[:5])}",
            payload={
                "run_id": result.run_id,
                "status": result.status,
                "errors": result.errors,
                "warnings": result.warnings,
                "report_paths": result.report_paths,
            },
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
