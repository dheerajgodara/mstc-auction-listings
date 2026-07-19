from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter, ValidationError

from scraper.batch_manifest import BATCH_STATUS_FAILED, BatchManifest
from scraper.qa_summary import run_strict_qa

IST = ZoneInfo("Asia/Kolkata")

_auctions_export_adapter = None


def _export_adapter():
    global _auctions_export_adapter
    if _auctions_export_adapter is None:
        from scraper.models import AuctionsExport

        _auctions_export_adapter = TypeAdapter(AuctionsExport)
    return _auctions_export_adapter


@dataclass
class SafetyGateConfig:
    min_count: int = 1000
    min_closing_date: str = ""
    max_drop_pct: float = 0.40
    max_mstc_drop_pct: float = 0.40
    allow_large_drop: bool = False
    require_sources: tuple[str, ...] = ("mstc", "eauction")
    warn_only_sources: tuple[str, ...] = ("gem_forward",)
    eauction_warn_only: bool = False
    allow_failed_batches: bool = False
    max_html_fail_rate_pct: float = 5.0
    max_pdf_fail_rate_pct: float = 5.0
    stale_warn_hours: float = 48.0
    stale_block_days: float = 7.0
    require_import_metadata: bool = True
    production_json: Path = Path("web/public/data/auctions.json")


@dataclass
class SafetyGateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    qa_report: dict = field(default_factory=dict)
    candidate_count: int = 0
    production_count: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    production_by_source: dict[str, int] = field(default_factory=dict)


def _load_counts(path: Path) -> tuple[int, dict[str, int]]:
    if not path.is_file():
        return 0, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    auctions = data.get("auctions", [])
    by_source = Counter(a.get("source", "missing") for a in auctions)
    count = int(data.get("count", len(auctions)))
    return count, dict(by_source)


def _check_drop(
    *,
    label: str,
    current: int,
    previous: int,
    max_drop_pct: float,
    allow_large_drop: bool,
    errors: list[str],
) -> None:
    if previous <= 0 or allow_large_drop:
        return
    threshold = previous * (1.0 - max_drop_pct)
    if current < threshold:
        errors.append(
            f"{label} count dropped more than {max_drop_pct * 100:.0f}%: "
            f"{previous} -> {current}"
        )


def _active_sources(by_source: dict[str, int]) -> set[str]:
    return {source for source, count in by_source.items() if count > 0}


def is_capped_mstc_only_export(by_source: dict[str, int], count: int) -> bool:
    """True when export looks like a legacy capped MSTC-only scrape.

    Historically a partial scrape capped near 500 MSTC rows with no GeM. During
    v3 cutover a healthy growing MSTC-only catalog is normal until GeM publishable
    catches up — do not block those.
    """
    if count <= 0 or count > 500:
        return False
    # Growing production / cutover catalogs: allow MSTC-only once past tiny exports.
    if count >= 100:
        return False
    active = _active_sources(by_source)
    return active == {"mstc"} and by_source.get("mstc", 0) == count


def _check_capped_mstc_only(by_source: dict[str, int], count: int, errors: list[str]) -> None:
    if is_capped_mstc_only_export(by_source, count):
        errors.append(
            "Refusing to deploy capped MSTC-only export. "
            f"count={count}, by_source={by_source}. "
            "Use refresh-and-deploy.yml for production."
        )


def _check_single_source_regression(
    cand_by_source: dict[str, int],
    prod_by_source: dict[str, int],
    *,
    allow_large_drop: bool,
    errors: list[str],
) -> None:
    if allow_large_drop:
        return
    prod_sources = _active_sources(prod_by_source)
    cand_sources = _active_sources(cand_by_source)
    if len(prod_sources) > 1 and len(cand_sources) <= 1:
        errors.append(
            "candidate has only one source but production had multiple sources: "
            f"production={sorted(prod_sources)}, candidate={sorted(cand_sources)}"
        )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(IST)
    except (TypeError, ValueError):
        return None


def _check_import_metadata(data: dict, errors: list[str]) -> None:
    if not data.get("automation_ran_at"):
        errors.append("candidate export missing automation_ran_at")
    if not data.get("run_id"):
        errors.append("candidate export missing run_id")
    auctions = data.get("auctions") or []
    missing = sum(1 for a in auctions if not (a.get("imported_at") or a.get("first_seen_at")))
    if missing:
        errors.append(f"{missing} auctions missing imported_at/first_seen_at")


def _check_stale_automation(
    data: dict,
    *,
    warn_hours: float,
    block_days: float,
    errors: list[str],
    warnings: list[str],
) -> None:
    ran_at = _parse_iso_datetime(data.get("automation_ran_at"))
    if ran_at is None:
        return
    age_hours = (datetime.now(IST) - ran_at).total_seconds() / 3600.0
    if age_hours > block_days * 24:
        errors.append(
            f"automation_ran_at is older than {block_days:.0f} days ({age_hours:.1f}h ago)"
        )
    elif age_hours > warn_hours:
        warnings.append(
            f"automation_ran_at is older than {warn_hours:.0f} hours ({age_hours:.1f}h ago)"
        )


def run_safety_gates(
    candidate: Path,
    *,
    config: SafetyGateConfig,
    batch_dir: Path | None = None,
    public_dir: Path | None = None,
) -> SafetyGateResult:
    errors: list[str] = []
    warnings: list[str] = []

    require_sources = list(config.require_sources)
    if config.eauction_warn_only and "eauction" in require_sources:
        require_sources = [s for s in require_sources if s != "eauction"]

    qa = run_strict_qa(
        candidate,
        min_count=config.min_count,
        min_closing_date=config.min_closing_date,
        require_sources=require_sources or None,
        warn_missing_sources=list(config.warn_only_sources),
        public_dir=public_dir,
    )
    errors.extend(qa.get("strict_errors", []))
    warnings.extend(qa.get("strict_warnings", []))

    if config.eauction_warn_only:
        by_source = qa.get("by_source", {})
        if by_source.get("eauction", 0) <= 0:
            warnings.append("eauction missing (warn-only mode)")

    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
        _export_adapter().validate_python(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        errors.append(f"JSON schema validation failed: {exc}")
        data = {}

    if data and config.require_import_metadata:
        _check_import_metadata(data, errors)
        _check_stale_automation(
            data,
            warn_hours=config.stale_warn_hours,
            block_days=config.stale_block_days,
            errors=errors,
            warnings=warnings,
        )

    prod_count, prod_by_source = _load_counts(config.production_json)
    cand_count = int(qa.get("total_auctions", 0))
    cand_by_source = qa.get("by_source", {})

    if cand_count <= 1:
        errors.append("accidental one-record candidate export")

    _check_capped_mstc_only(cand_by_source, cand_count, errors)
    _check_single_source_regression(
        cand_by_source,
        prod_by_source,
        allow_large_drop=config.allow_large_drop,
        errors=errors,
    )

    _check_drop(
        label="Total",
        current=cand_count,
        previous=prod_count,
        max_drop_pct=config.max_drop_pct,
        allow_large_drop=config.allow_large_drop,
        errors=errors,
    )
    _check_drop(
        label="MSTC",
        current=cand_by_source.get("mstc", 0),
        previous=prod_by_source.get("mstc", 0),
        max_drop_pct=config.max_mstc_drop_pct,
        allow_large_drop=config.allow_large_drop,
        errors=errors,
    )

    html_rate = float(qa.get("html_fail_rate_pct", 0) or 0)
    pdf_rate = float(qa.get("pdf_fail_rate_pct", 0) or 0)
    if html_rate > config.max_html_fail_rate_pct:
        errors.append(f"HTML failure rate {html_rate}% exceeds {config.max_html_fail_rate_pct}%")
    if pdf_rate > config.max_pdf_fail_rate_pct:
        errors.append(f"PDF failure rate {pdf_rate}% exceeds {config.max_pdf_fail_rate_pct}%")

    if batch_dir and batch_dir.is_dir():
        manifest_path = batch_dir / "manifest.json"
        if manifest_path.is_file():
            manifest = BatchManifest.load_or_create(manifest_path)
            failed_mstc = [
                b
                for b in manifest.data.get("batches", [])
                if b.get("source") == "mstc" and b.get("status") == BATCH_STATUS_FAILED
            ]
            if failed_mstc and not config.allow_failed_batches:
                ids = ", ".join(b.get("batch_id", "?") for b in failed_mstc)
                errors.append(f"failed MSTC office batches: {ids}")

    return SafetyGateResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        qa_report=qa,
        candidate_count=cand_count,
        production_count=prod_count,
        by_source=cand_by_source,
        production_by_source=prod_by_source,
    )
