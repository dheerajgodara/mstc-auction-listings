"""Verify live export freshness and minimum auction count."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.error import URLError
from urllib.request import urlopen

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class FreshnessResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    automation_ran_at: str | None = None
    count: int | None = None
    age_hours: float | None = None


def check_freshness(
    *,
    base_url: str,
    max_age_hours: float = 36.0,
    min_count: int = 1000,
    warn_only: bool = False,
) -> FreshnessResult:
    """Fetch export-meta.json from a deployed site and validate freshness."""
    errors: list[str] = []
    warnings: list[str] = []
    meta_url = base_url.rstrip("/") + "/data/export-meta.json"
    automation_ran_at: str | None = None
    count: int | None = None
    age_hours: float | None = None

    try:
        with urlopen(meta_url, timeout=30) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, json.JSONDecodeError) as exc:
        errors.append(f"Failed to fetch {meta_url}: {exc}")
        return FreshnessResult(passed=False, errors=errors)

    automation_ran_at = meta.get("automation_ran_at") or meta.get("generated_at")
    count = int(meta.get("count") or 0)

    if count < min_count:
        msg = f"count {count} below minimum {min_count}"
        if warn_only:
            warnings.append(msg)
        else:
            errors.append(msg)

    if not automation_ran_at:
        errors.append("missing automation_ran_at in export-meta.json")
    else:
        try:
            dt = datetime.fromisoformat(str(automation_ran_at))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            age = datetime.now(IST) - dt.astimezone(IST)
            age_hours = age.total_seconds() / 3600.0
            if age > timedelta(hours=max_age_hours):
                msg = (
                    f"automation_ran_at is {age_hours:.1f}h old "
                    f"(limit {max_age_hours}h)"
                )
                if warn_only:
                    warnings.append(msg)
                else:
                    errors.append(msg)
        except ValueError:
            errors.append(f"invalid automation_ran_at: {automation_ran_at}")

    passed = len(errors) == 0
    return FreshnessResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        automation_ran_at=str(automation_ran_at) if automation_ran_at else None,
        count=count,
        age_hours=age_hours,
    )


def main(argv: list[str] | None = None) -> int:
    from scraper.config import SITE_BASE_URL

    parser = argparse.ArgumentParser(description="Check live auction export freshness")
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL or "https://scrapauctionindia.com/auctions",
    )
    parser.add_argument("--max-age-hours", type=float, default=36.0)
    parser.add_argument("--min-count", type=int, default=1000)
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args(argv)

    result = check_freshness(
        base_url=args.base_url,
        max_age_hours=args.max_age_hours,
        min_count=args.min_count,
        warn_only=args.warn_only,
    )
    for warn in result.warnings:
        print(f"WARN: {warn}")
    for err in result.errors:
        print(f"ERROR: {err}")
    if result.automation_ran_at:
        print(f"automation_ran_at={result.automation_ran_at} count={result.count}")
    if result.age_hours is not None:
        print(f"age_hours={result.age_hours:.1f}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
