"""QA summary and strict validation for auctions.json exports."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.filters import parse_min_closing_boundary

IST = ZoneInfo("Asia/Kolkata")

SECTION_KEYS = (
    "lot_details_text",
    "lot_description_text",
    "lot_parameters_text",
    "lot_other_details_text",
    "lot_documents_text",
)


def _has_text(value: object) -> bool:
    return bool(value and str(value).strip())


def _parse_closing(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(IST) if value.tzinfo else value.replace(tzinfo=IST)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt.astimezone(IST) if dt.tzinfo else dt.replace(tzinfo=IST)
    return None


def _iter_string_values(obj: object):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_string_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_string_values(item)


def _site_root_asset_prefix(value: str) -> str | None:
    """Return /pdfs|/docs|/thumbs when value is site-root path, not CDN URL."""
    s = str(value or "").strip()
    if not s or s.startswith(("http://", "https://")):
        return None
    for bad in ("/pdfs/", "/docs/", "/thumbs/"):
        if s.startswith(bad):
            return bad
    return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_asset(path_str: str, *, public_dir: Path) -> Path | None:
    if not path_str or path_str.startswith("http"):
        return None
    clean = path_str.lstrip("/")
    if clean.startswith("auctions/"):
        clean = clean[len("auctions/") :]
    return public_dir / clean


def analyze(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    auctions = data.get("auctions", [])
    stats = data.get("stats", {})
    lots = [lot for a in auctions for lot in a.get("lots", [])]

    lot_sections = {
        "all_five": sum(1 for lot in lots if all(_has_text(lot.get(k)) for k in SECTION_KEYS)),
        "missing_details": sum(1 for lot in lots if not _has_text(lot.get("lot_details_text"))),
        "missing_description": sum(
            1 for lot in lots if not _has_text(lot.get("lot_description_text"))
        ),
        "missing_parameters": sum(
            1 for lot in lots if not _has_text(lot.get("lot_parameters_text"))
        ),
        "missing_other_details": sum(
            1 for lot in lots if not _has_text(lot.get("lot_other_details_text"))
        ),
        "missing_documents": sum(
            1 for lot in lots if not _has_text(lot.get("lot_documents_text"))
        ),
    }

    confidence = Counter(a.get("parse_confidence") for a in auctions)
    emd_status = Counter(a.get("emd_parse_status") for a in auctions)
    price_status = Counter(a.get("price_parse_status") for a in auctions)
    by_source = Counter(a.get("source", "missing") for a in auctions)

    total_auctions = len(auctions)
    html_fail = stats.get("html_failures", 0)
    pdf_fail = stats.get("pdf_failures", 0)
    html_rate = (html_fail / total_auctions * 100) if total_auctions else 0
    pdf_rate = (pdf_fail / total_auctions * 100) if total_auctions else 0
    low_minimal = confidence.get("low", 0) + confidence.get("minimal", 0)
    low_minimal_rate = (low_minimal / total_auctions * 100) if total_auctions else 0

    thresholds_ok = (
        html_rate <= 5
        and pdf_rate <= 5
        and low_minimal_rate <= 10
        and lot_sections["all_five"] >= max(1, len(lots) * 0.5)
    )

    return {
        "path": str(path),
        "total_auctions": total_auctions,
        "total_lots": len(lots),
        "by_source": dict(by_source),
        "pdf_downloaded": stats.get("pdf_downloaded", 0),
        "pdf_cache_hits": stats.get("pdf_cache_hits", 0),
        "html_failures": html_fail,
        "pdf_failures": pdf_fail,
        "html_fail_rate_pct": round(html_rate, 2),
        "pdf_fail_rate_pct": round(pdf_rate, 2),
        "confidence": dict(confidence),
        "emd_status": dict(emd_status),
        "price_status": dict(price_status),
        "documents": stats.get("documents", {}),
        "missing_location": sum(1 for a in auctions if not a.get("location")),
        "missing_lots": sum(1 for a in auctions if not a.get("lots")),
        "missing_price_status": sum(
            1 for a in auctions if a.get("price_parse_status") == "missing"
        ),
        "missing_emd_status": sum(
            1 for a in auctions if a.get("emd_parse_status") == "missing"
        ),
        "missing_field_counts": stats.get("missing_field_counts", {}),
        "extraction_errors": stats.get("extraction_errors", []),
        "lot_sections": lot_sections,
        "low_minimal_rate_pct": round(low_minimal_rate, 2),
        "thresholds_ok": thresholds_ok,
        "closing_bounds": stats.get("closing_bounds", {}),
        "future_filter": stats.get("future_filter", {}),
    }


def run_strict_qa(
    path: Path,
    *,
    min_count: int = 1000,
    min_closing_date: str | None = None,
    require_sources: list[str] | None = None,
    warn_missing_sources: list[str] | None = None,
    public_dir: Path | None = None,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    public = public_dir or (_repo_root() / "web" / "public")

    if not path.is_file():
        return {"passed": False, "errors": [f"File not found: {path}"], "warnings": warnings}

    data = json.loads(path.read_text(encoding="utf-8"))
    auctions = data.get("auctions", [])
    count = data.get("count", len(auctions))

    if count != len(auctions):
        errors.append(f"count mismatch: header={count} actual={len(auctions)}")
    if count < min_count:
        errors.append(f"count {count} below min-count {min_count}")
    # Cutover / empty publishable set: min_count=0 allows empty export.
    if count == 1 and min_count > 0:
        errors.append("accidental one-record export detected")
    elif count == 0 and min_count > 0:
        errors.append(f"count {count} below min-count {min_count}")

    by_source = Counter(a.get("source", "missing") for a in auctions)
    if require_sources:
        for source in require_sources:
            if by_source.get(source, 0) <= 0:
                errors.append(f"required source missing: {source}")
    if warn_missing_sources:
        for source in warn_missing_sources:
            if by_source.get(source, 0) <= 0:
                warnings.append(f"optional source missing: {source}")

    min_closing = parse_min_closing_boundary(min_closing_date) if min_closing_date else None
    earliest: datetime | None = None
    for auction in auctions:
        if not auction.get("source"):
            errors.append(f"record {auction.get('id')} missing source")
        closing = _parse_closing(auction.get("closing"))
        if closing is None:
            errors.append(f"record {auction.get('id')} missing closing")
            continue
        if earliest is None or closing < earliest:
            earliest = closing
        if min_closing and closing < min_closing:
            errors.append(f"record {auction.get('id')} closes before {min_closing_date}: {closing.isoformat()}")

        blob = json.dumps(auction)
        for val in _iter_string_values(auction):
            bad = _site_root_asset_prefix(val)
            if bad:
                errors.append(f"record {auction.get('id')} contains absolute path {bad}")
                break

    auction_587164 = next((a for a in auctions if a.get("id") == "587164"), None)
    if auction_587164:
        if not auction_587164.get("lots"):
            errors.append("587164 regression: missing lots")
        else:
            lot = auction_587164["lots"][0]
            for key in SECTION_KEYS:
                if not _has_text(lot.get(key)):
                    errors.append(f"587164 regression: missing {key}")
            if not lot.get("preview_images"):
                errors.append("587164 regression: missing preview_images")

    for auction in auctions:
        if auction.get("source") != "mstc":
            continue
        for lot in auction.get("lots", []):
            for img in lot.get("preview_images") or []:
                url = img if isinstance(img, str) else (img.get("url") or img.get("thumbnail_url") or "")
                if _site_root_asset_prefix(str(url or "")):
                    errors.append(f"absolute preview path on {auction.get('id')}")

    report = analyze(path)
    report["strict_errors"] = errors
    report["strict_warnings"] = warnings
    report["earliest_closing"] = earliest.isoformat() if earliest else None
    report["passed"] = not errors
    return report


def print_report(report: dict) -> None:
    print("=== Auction QA Summary ===")
    print(f"File: {report['path']}")
    print(f"Total auctions: {report['total_auctions']}")
    print(f"Total lots: {report['total_lots']}")
    print(f"By source: {report.get('by_source', {})}")
    if report.get("earliest_closing"):
        print(f"Earliest closing: {report['earliest_closing']}")
    print(
        f"PDFs downloaded: {report['pdf_downloaded']} | cache hits: {report['pdf_cache_hits']}"
    )
    print(
        f"HTML failures: {report['html_failures']} ({report['html_fail_rate_pct']}%)"
    )
    print(f"PDF failures: {report['pdf_failures']} ({report['pdf_fail_rate_pct']}%)")
    if report.get("documents"):
        print(f"Documents: {report['documents']}")
    ls = report["lot_sections"]
    print(f"Lots with all 5 raw sections: {ls['all_five']}")
    print(f"Quality thresholds OK: {report['thresholds_ok']}")
    if report.get("strict_errors"):
        print("STRICT QA ERRORS:")
        for err in report["strict_errors"]:
            print(f"  - {err}")
    if report.get("strict_warnings"):
        print("Warnings:")
        for warn in report["strict_warnings"]:
            print(f"  - {warn}")
    print(f"Strict QA passed: {report.get('passed', report['thresholds_ok'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QA summary for auctions.json")
    parser.add_argument("--json", type=Path, default=Path("work/future_full_auctions.json"))
    parser.add_argument("--fail-on-threshold", action="store_true")
    parser.add_argument("--min-count", type=int, default=None)
    parser.add_argument("--min-closing-date", type=str, default=None)
    parser.add_argument("--require-sources", type=str, default=None)
    parser.add_argument("--warn-missing-source", action="append", default=[])
    args = parser.parse_args(argv)

    if not args.json.is_file():
        print(f"ERROR: {args.json} not found", file=sys.stderr)
        return 1

    if args.min_count is not None or args.min_closing_date or args.require_sources:
        require = [s.strip() for s in (args.require_sources or "").split(",") if s.strip()]
        report = run_strict_qa(
            args.json,
            min_count=args.min_count or 1,
            min_closing_date=args.min_closing_date,
            require_sources=require or None,
            warn_missing_sources=args.warn_missing_source or None,
        )
    else:
        report = analyze(args.json)
        report["passed"] = report["thresholds_ok"]

    print_report(report)
    if args.fail_on_threshold and not report.get("passed"):
        return 1
    if args.min_count is not None and not report.get("passed"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
