from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.filters import parse_min_closing_date
from scraper.qa_summary import _parse_closing
from scraper.safety_gates import is_capped_mstc_only_export

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class PredeployVerifyResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    count: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    earliest_closing: str | None = None
    pdf_count: int = 0
    docs_count: int = 0
    thumbs_count: int = 0


def _count_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.rglob("*") if p.is_file())


def _relative_asset_exists(out_dir: Path, rel_url: str) -> bool:
    rel = rel_url.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    if rel.startswith(("http://", "https://")):
        return True
    return (out_dir / rel).is_file()


def verify_predeploy_build(
    *,
    out_dir: Path,
    min_count: int,
    min_closing_date: str,
    require_sources: list[str],
    warn_only_sources: list[str] | None = None,
) -> PredeployVerifyResult:
    errors: list[str] = []
    warnings: list[str] = []

    index_html = out_dir / "index.html"
    json_path = out_dir / "data" / "auctions.json"
    pdfs_dir = out_dir / "pdfs"
    docs_dir = out_dir / "docs"
    thumbs_dir = out_dir / "thumbs"

    if not index_html.is_file():
        errors.append(f"missing {index_html}")
    if not json_path.is_file():
        errors.append(f"missing {json_path}")
    if not pdfs_dir.is_dir():
        errors.append(f"missing {pdfs_dir}")
    if not docs_dir.is_dir():
        warnings.append(f"missing {docs_dir}")
    if not thumbs_dir.is_dir():
        warnings.append(f"missing {thumbs_dir}")

    count = 0
    by_source: dict[str, int] = {}
    earliest: datetime | None = None
    if json_path.is_file():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        auctions = data.get("auctions", [])
        count = int(data.get("count", len(auctions)))
        if count != len(auctions):
            errors.append(f"count mismatch in build output: header={count} actual={len(auctions)}")
        if count < min_count:
            errors.append(f"build count {count} below min-count {min_count}")
        if count <= 1:
            errors.append("accidental one-record build export")

        by_source = dict(Counter(a.get("source", "missing") for a in auctions))
        min_closing = parse_min_closing_date(min_closing_date)
        for auction in auctions:
            closing = _parse_closing(auction.get("closing"))
            if closing is None:
                errors.append(f"record {auction.get('id')} missing closing")
                continue
            if earliest is None or closing < earliest:
                earliest = closing
            if closing < min_closing:
                errors.append(
                    f"record {auction.get('id')} closes before {min_closing_date}: {closing.isoformat()}"
                )

        for source in require_sources:
            if by_source.get(source, 0) <= 0:
                errors.append(f"required source missing in build: {source}")
        for source in warn_only_sources or []:
            if by_source.get(source, 0) <= 0:
                warnings.append(f"optional source missing in build: {source}")

        if is_capped_mstc_only_export(by_source, count):
            errors.append(
                "Refusing to deploy capped MSTC-only export. "
                f"count={count}, by_source={by_source}. "
                "Use refresh-and-deploy.yml for production."
            )

        missing_pdfs: list[str] = []
        for auction in auctions:
            pdf_url = auction.get("pdf_url")
            if pdf_url and str(pdf_url).startswith("pdfs/") and not _relative_asset_exists(out_dir, str(pdf_url)):
                missing_pdfs.append(f"{auction.get('id')}:{pdf_url}")
        if missing_pdfs:
            sample = ", ".join(missing_pdfs[:10])
            extra = "" if len(missing_pdfs) <= 10 else f" (+{len(missing_pdfs) - 10} more)"
            errors.append(f"build has auction PDF links without files: {sample}{extra}")

    pdf_count = _count_files(pdfs_dir)
    docs_count = _count_files(docs_dir)
    thumbs_count = _count_files(thumbs_dir)
    if pdf_count < 10 and count >= min_count:
        warnings.append(f"suspiciously low PDF count in build: {pdf_count}")

    return PredeployVerifyResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        count=count,
        by_source=by_source,
        earliest_closing=earliest.isoformat() if earliest else None,
        pdf_count=pdf_count,
        docs_count=docs_count,
        thumbs_count=thumbs_count,
    )
