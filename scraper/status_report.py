from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scraper.config import REPO_ROOT, SITE_BASE_URL
from scraper.http_verify import verify_live_site
from scraper.refresh_reports import load_latest_run, load_production_summary


def _count_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.rglob("*") if p.is_file())


def _local_build_metrics(repo_root: Path) -> dict:
    out_index = repo_root / "web" / "out" / "index.html"
    out_data_js = repo_root / "web" / "out" / "data" / "auctions-data.js"
    out_json = repo_root / "web" / "out" / "data" / "auctions.json"
    metrics: dict = {
        "index_html_bytes": None,
        "auctions_data_js_bytes": None,
        "auctions_json_bytes": None,
        "local_build_present": out_index.is_file(),
    }
    if out_index.is_file():
        metrics["index_html_bytes"] = out_index.stat().st_size
    if out_data_js.is_file():
        metrics["auctions_data_js_bytes"] = out_data_js.stat().st_size
    if out_json.is_file():
        metrics["auctions_json_bytes"] = out_json.stat().st_size
    return metrics


def build_status_report(
    *,
    repo_root: Path,
    check_live: bool = False,
) -> dict:
    production_json = repo_root / "web" / "public" / "data" / "auctions.json"
    latest = load_latest_run(repo_root / "work" / "runs")
    latest_success = None
    success_path = repo_root / "work" / "runs" / "latest_successful.json"
    if success_path.is_file():
        latest_success = json.loads(success_path.read_text(encoding="utf-8"))

    production = load_production_summary(production_json)
    if production_json.is_file():
        try:
            raw = json.loads(production_json.read_text(encoding="utf-8"))
            production["generated_at"] = raw.get("generated_at")
        except json.JSONDecodeError:
            pass

    warnings: list[str] = []
    local_build = _local_build_metrics(repo_root)

    report = {
        "production": production,
        "assets": {
            "pdfs": _count_files(repo_root / "web" / "public" / "pdfs"),
            "docs": _count_files(repo_root / "web" / "public" / "docs"),
            "thumbs": _count_files(repo_root / "web" / "public" / "thumbs"),
        },
        "local_build": local_build,
        "last_run": latest,
        "last_successful_deploy": latest_success,
        "warnings": warnings,
        "live_http": None,
    }

    if production["count"] <= 1:
        warnings.append("production JSON has suspiciously low count")
    if latest and latest.get("status") == "failed":
        warnings.append(f"last refresh run failed: {latest.get('run_id')}")
    if local_build.get("index_html_bytes") and local_build["index_html_bytes"] > 500_000:
        warnings.append(
            f"local index.html is large ({local_build['index_html_bytes']} bytes); "
            "expected client-side data loading shell"
        )

    if check_live:
        http = verify_live_site(
            base_url=SITE_BASE_URL or None,
            expected_count=production.get("count"),
            candidate_json=production_json if production_json.is_file() else None,
        )
        report["live_http"] = {
            "passed": http.passed,
            "index_status": http.index_status,
            "json_status": http.json_status,
            "data_js_status": http.data_js_status,
            "live_count_hint": http.live_count_hint,
            "checked_urls": http.checked_urls,
            "errors": http.errors,
            "warnings": http.warnings,
        }
        warnings.extend(http.warnings)
        if http.index_status != 200:
            warnings.append(f"live index HTTP {http.index_status}")
        if http.data_js_status not in (None, 200):
            warnings.append(f"live auctions-data.js HTTP {http.data_js_status}")

    report["warnings"] = warnings
    return report


def print_status_report(report: dict) -> None:
    prod = report.get("production", {})
    print("=== Auction Site Status ===")
    print(f"Production count: {prod.get('count')}")
    print(f"By source: {prod.get('by_source')}")
    print(f"Earliest closing: {prod.get('earliest_closing')}")
    print(f"Total lots: {prod.get('total_lots')}")
    print(f"Generated at: {prod.get('generated_at')}")
    assets = report.get("assets", {})
    print(f"Assets — PDFs: {assets.get('pdfs')} docs: {assets.get('docs')} thumbs: {assets.get('thumbs')}")

    local = report.get("local_build") or {}
    if local.get("local_build_present"):
        print(f"Local index.html: {local.get('index_html_bytes')} bytes")
        if local.get("auctions_data_js_bytes") is not None:
            print(f"Local auctions-data.js: {local.get('auctions_data_js_bytes')} bytes")

    last = report.get("last_run")
    if last:
        deploy = last.get("deploy") or {}
        print(
            f"Last run: {last.get('run_id')} status={last.get('status')} "
            f"deployed={deploy.get('deployed')} finished={last.get('finished_at')}"
        )
    else:
        print("Last run: (none recorded)")

    success = report.get("last_successful_deploy")
    if success:
        print(
            f"Last successful deploy: run={success.get('run_id')} "
            f"count={success.get('total_auctions')} finished={success.get('finished_at')}"
        )

    live = report.get("live_http")
    if live:
        print(f"Live index HTTP: {live.get('index_status')}")
        print(f"Live JSON HTTP: {live.get('json_status')}")
        print(f"Live auctions-data.js HTTP: {live.get('data_js_status')}")
        if live.get("live_count_hint") is not None:
            print(f"Live count hint: {live.get('live_count_hint')}")

    warnings = report.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warn in warnings:
            print(f"  - {warn}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Status report for auction refresh automation")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--check-live", action="store_true", help="Probe live site over HTTP")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    report = build_status_report(repo_root=args.repo_root, check_live=args.check_live)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_status_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
