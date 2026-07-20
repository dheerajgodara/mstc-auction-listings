from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.filters import parse_min_closing_boundary
from scraper.qa_summary import _parse_closing
from scraper.safety_gates import is_capped_mstc_only_export


def _predeploy_docs_mode() -> str:
    """warn (default) or fail — set PREDEPLOY_DOCS_MODE=fail after media backfill."""
    raw = (os.environ.get("PREDEPLOY_DOCS_MODE") or "warn").strip().lower()
    return "fail" if raw == "fail" else "warn"

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


def _is_cdn_media_url(url: str) -> bool:
    raw = str(url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return False
    from scraper.config import R2_PUBLIC_BASE_URL

    base = (R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base and raw.startswith(base + "/"):
        return True
    return "files.csmg.in/" in raw or "files.scrapauctionindia.com/" in raw or ".r2.dev/" in raw


def _relative_asset_exists(out_dir: Path, rel_url: str) -> bool:
    rel = rel_url.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    if rel.startswith(("http://", "https://")):
        # Absolute media URLs live on CDN; local file not required in build out.
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

    allow_small = (os.environ.get("PIPELINE_ALLOW_SMALL_EXPORT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    media_r2_only = (os.environ.get("MEDIA_R2_ONLY") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if not index_html.is_file():
        errors.append(f"missing {index_html}")
    if not json_path.is_file():
        errors.append(f"missing {json_path}")
    if not pdfs_dir.is_dir():
        if media_r2_only or allow_small:
            warnings.append(f"missing {pdfs_dir} (CDN-only / small export)")
        else:
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
        effective_min = 0 if allow_small else min_count
        if count < effective_min:
            errors.append(f"build count {count} below min-count {effective_min}")
        if count <= 1 and not allow_small:
            errors.append("accidental one-record build export")

        by_source = dict(Counter(a.get("source", "missing") for a in auctions))
        min_closing = parse_min_closing_boundary(min_closing_date)
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
            if by_source.get(source, 0) <= 0 and not allow_small:
                errors.append(f"required source missing in build: {source}")
        for source in warn_only_sources or []:
            if by_source.get(source, 0) <= 0:
                warnings.append(f"optional source missing in build: {source}")

        if not allow_small and is_capped_mstc_only_export(by_source, count):
            errors.append(
                "Refusing to deploy capped MSTC-only export. "
                f"count={count}, by_source={by_source}. "
                "Use refresh-and-deploy.yml for production."
            )

        missing_pdfs: list[str] = []
        missing_hostinger: list[str] = []
        missing_lots: list[str] = []
        for auction in auctions:
            aid = auction.get("id") or auction.get("source_auction_id")
            lots = auction.get("lots") or []
            if not isinstance(lots, list) or not lots:
                missing_lots.append(str(aid))
            host = (
                auction.get("object_doc_url")
                or auction.get("hostinger_doc_url")
                or auction.get("pdf_url")
            )
            if not host:
                missing_hostinger.append(str(aid))
            pdf_url = auction.get("pdf_url")
            pdf_s = str(pdf_url or "")
            if _is_cdn_media_url(pdf_s):
                pass
            elif pdf_url and str(pdf_url).startswith("pdfs/") and not _relative_asset_exists(
                out_dir, str(pdf_url)
            ):
                missing_pdfs.append(f"{aid}:{pdf_url}")
            elif pdf_url and str(pdf_url).startswith("docs/") and not _relative_asset_exists(
                out_dir, str(pdf_url)
            ):
                missing_pdfs.append(f"{aid}:{pdf_url}")
        if missing_lots:
            sample = ", ".join(missing_lots[:10])
            errors.append(f"v3 gate: auctions without lots (not publishable): {sample}")
        if missing_hostinger:
            sample = ", ".join(missing_hostinger[:10])
            errors.append(
                f"v3 gate: auctions without CDN/media doc URL (not publishable): {sample}"
            )
        if missing_pdfs:
            sample = ", ".join(missing_pdfs[:10])
            extra = "" if len(missing_pdfs) <= 10 else f" (+{len(missing_pdfs) - 10} more)"
            errors.append(f"build has auction PDF links without files: {sample}{extra}")

        missing_lot_docs: list[str] = []
        for auction in auctions:
            for lot in auction.get("lots") or []:
                if not isinstance(lot, dict):
                    continue
                for doc in lot.get("documents") or []:
                    if not isinstance(doc, dict):
                        continue
                    status = doc.get("status")
                    if status not in {"downloaded", "thumbnail_ready"}:
                        continue
                    for field_name in ("cached_url", "thumbnail_url"):
                        url = doc.get(field_name)
                        if not url:
                            continue
                        rel = str(url).lstrip("/")
                        if not (
                            rel.startswith("docs/")
                            or rel.startswith("thumbs/")
                            or rel.startswith("pdfs/")
                        ):
                            continue
                        if not _relative_asset_exists(out_dir, rel):
                            missing_lot_docs.append(
                                f"{auction.get('id')}:{field_name}:{rel}"
                            )
        if missing_lot_docs:
            sample = ", ".join(missing_lot_docs[:10])
            extra = (
                ""
                if len(missing_lot_docs) <= 10
                else f" (+{len(missing_lot_docs) - 10} more)"
            )
            msg = (
                f"build has lot.documents links without files "
                f"({len(missing_lot_docs)}): {sample}{extra}"
            )
            if _predeploy_docs_mode() == "fail":
                errors.append(msg)
            else:
                warnings.append(msg)

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
