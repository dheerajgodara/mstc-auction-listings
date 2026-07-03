from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from scraper.batch_manifest import BATCH_STATUS_FAILED, BatchManifest
from scraper.qa_summary import run_strict_qa

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

    prod_count, prod_by_source = _load_counts(config.production_json)
    cand_count = int(qa.get("total_auctions", 0))
    cand_by_source = qa.get("by_source", {})

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
