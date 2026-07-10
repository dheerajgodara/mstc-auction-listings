from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

LATEST_JSON = Path("work/runs/latest.json")
LATEST_SUCCESS_JSON = Path("work/runs/latest_successful.json")


def _now_iso() -> str:
    return datetime.now(IST).isoformat()


def write_final_reports(
    *,
    reports_dir: Path,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "final_report.json"
    md_path = reports_dir / "final_report.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_final_report_md(payload), encoding="utf-8")
    return md_path, json_path


def render_final_report_md(payload: dict[str, Any]) -> str:
    deploy = payload.get("deploy") or {}
    deployed = deploy.get("deployed")
    lines = [
        "# Refresh Run Report",
        "",
        f"- **Run ID:** {payload.get('run_id')}",
        f"- **Status:** {payload.get('status')}",
        f"- **Deploy requested:** {payload.get('deploy_requested')}",
        f"- **Deployed:** {deployed if deployed is not None else 'n/a'}",
        f"- **Started:** {payload.get('started_at')}",
        f"- **Finished:** {payload.get('finished_at')}",
        f"- **Min closing date:** {payload.get('min_closing_date')}",
        "",
        "## Counts",
        "",
        f"- Total auctions: {payload.get('total_auctions')}",
        f"- Total lots: {payload.get('total_lots')}",
        f"- By source: {payload.get('by_source')}",
        "",
    ]

    doc_recovery = payload.get("document_recovery") or {}
    if doc_recovery:
        lines.extend(["## Document recovery", ""])
        lines.append(f"- Failed downloads (total): {doc_recovery.get('failed_total', 0)}")
        too_small = doc_recovery.get("too_small", 0)
        if too_small:
            lines.append(f"- **too_small** (HTML error pages): {too_small}")
        by_reason = doc_recovery.get("failed_by_reason") or {}
        if by_reason:
            lines.append(f"- By reason: {by_reason}")
        by_type = doc_recovery.get("failed_by_doc_type") or {}
        if by_type:
            lines.append(f"- By doc type: {by_type}")
        lines.append(
            "- Note: document download failures do not fail auction extraction; "
            "auctions remain listed with available metadata."
        )
        lines.append("")

    lines.extend(["## Pipeline", ""])
    for step in (
        "discovery",
        "incremental_work_plan",
        "batch_scrape",
        "merge",
        "incremental_materialize",
        "previous_production_bootstrap",
        "source_fallback",
        "candidate_finalization",
        "qa",
        "safety_gates",
        "promotion",
        "build",
        "predeploy",
        "deploy",
        "http_verify",
    ):
        step_data = payload.get(step) or {}
        if step_data:
            lines.append(f"### {step.replace('_', ' ').title()}")
            for key, value in step_data.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

    warnings = payload.get("warnings") or []
    errors = payload.get("errors") or []
    if warnings:
        lines.extend(["## Warnings", ""])
        for warn in warnings:
            lines.append(f"- {warn}")
        lines.append("")
    if errors:
        lines.extend(["## Errors", ""])
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    if payload.get("rollback_backup_path"):
        lines.append(f"**Rollback backup:** `{payload['rollback_backup_path']}`")
    if payload.get("previous_production_backup_path"):
        lines.append(f"**Previous production backup:** `{payload['previous_production_backup_path']}`")

    return "\n".join(lines) + "\n"


def update_latest_run(
    *,
    runs_root: Path,
    payload: dict[str, Any],
    success: bool,
) -> Path:
    runs_root.mkdir(parents=True, exist_ok=True)
    latest_path = runs_root / "latest.json"
    latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if success:
        success_path = runs_root / "latest_successful.json"
        success_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return latest_path


def load_latest_run(runs_root: Path | None = None) -> dict[str, Any] | None:
    path = (runs_root or Path("work/runs")) / "latest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_production_summary(production_json: Path) -> dict[str, Any]:
    if not production_json.is_file():
        return {"count": 0, "by_source": {}, "earliest_closing": None, "total_lots": 0}
    data = json.loads(production_json.read_text(encoding="utf-8"))
    from collections import Counter

    from scraper.qa_summary import _parse_closing

    auctions = data.get("auctions", [])
    by_source = dict(Counter(a.get("source", "missing") for a in auctions))
    earliest = None
    for auction in auctions:
        closing = _parse_closing(auction.get("closing"))
        if closing and (earliest is None or closing < earliest):
            earliest = closing
    return {
        "count": int(data.get("count", len(auctions))),
        "by_source": by_source,
        "earliest_closing": earliest.isoformat() if earliest else None,
        "total_lots": sum(len(a.get("lots", [])) for a in auctions),
        "generated_at": data.get("generated_at"),
    }
