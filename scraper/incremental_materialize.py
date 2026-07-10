from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.export_guard import write_auctions_json
from scraper.incremental import build_record_index, load_export, stable_listing_key
from scraper.incremental_plan import IncrementalWorkPlan, load_work_plan

IST = ZoneInfo("Asia/Kolkata")


def _count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        counter[str(record.get(field) or "unknown")] += 1
    return dict(counter)


def materialize_incremental_export(
    *,
    work_plan: IncrementalWorkPlan,
    previous_export: dict[str, Any],
    parsed_export: dict[str, Any],
    discovery_export: dict[str, Any] | None = None,
    allow_missing_deep_parse: bool = False,
) -> dict[str, Any]:
    previous_idx = build_record_index(previous_export)
    parsed_idx = build_record_index(parsed_export)
    discovery_idx = build_record_index(discovery_export) if discovery_export else {}

    records: list[dict[str, Any]] = []
    missing_deep_parse: list[str] = []
    reused = 0
    reused_discovery = 0
    deep_used = 0
    removed = 0

    for item in work_plan.items:
        if item.action == "reuse_previous":
            previous_record = previous_idx.get(item.stable_key)
            if previous_record:
                records.append(previous_record)
                reused += 1
            else:
                missing_deep_parse.append(item.stable_key)
        elif item.action == "deep_parse":
            parsed_record = parsed_idx.get(item.stable_key)
            if parsed_record:
                records.append(parsed_record)
                deep_used += 1
            elif allow_missing_deep_parse:
                previous_record = previous_idx.get(item.stable_key)
                if previous_record:
                    records.append(previous_record)
                    reused += 1
                    missing_deep_parse.append(item.stable_key)
                else:
                    discovery_record = discovery_idx.get(item.stable_key)
                    if discovery_record:
                        records.append(_mark_pending_shallow(discovery_record))
                        reused_discovery += 1
                        missing_deep_parse.append(item.stable_key)
            else:
                missing_deep_parse.append(item.stable_key)
        elif item.action == "reuse_discovery":
            discovery_record = discovery_idx.get(item.stable_key)
            previous_record = previous_idx.get(item.stable_key)
            if discovery_record:
                records.append(_mark_pending_shallow(discovery_record))
                reused_discovery += 1
            elif previous_record:
                records.append(previous_record)
                reused += 1
                missing_deep_parse.append(item.stable_key)
            else:
                missing_deep_parse.append(item.stable_key)
        elif item.action == "mark_removed":
            removed += 1

    if missing_deep_parse and not allow_missing_deep_parse:
        raise ValueError(f"Missing parsed records for {len(missing_deep_parse)} work-plan item(s): {missing_deep_parse[:10]}")

    records.sort(key=lambda r: r.get("closing") or "")
    generated_at = parsed_export.get("generated_at") or datetime.now(IST).isoformat()
    stats = dict(parsed_export.get("stats") or {})
    stats["incremental_materialize"] = {
        "enabled": True,
        "work_plan_generated_at": work_plan.generated_at,
        "reused_previous_records": reused,
        "reused_discovery_records": reused_discovery,
        "deep_parsed_records": deep_used,
        "removed_records": removed,
        "missing_deep_parse_records": len(missing_deep_parse),
        "missing_deep_parse_keys": missing_deep_parse[:50],
        "action_counts": work_plan.action_counts,
    }
    stats["by_source"] = _count_by(records, "source")
    stats["by_category"] = _count_by(records, "asset_category")
    stats["total_lots_in_export"] = sum(len(r.get("lots") or []) for r in records)

    return {
        "generated_at": generated_at,
        "count": len(records),
        "auctions": records,
        "stats": stats,
    }


def _needs_shallow_placeholder(record: dict[str, Any]) -> bool:
    status = str(record.get("status") or "").lower()
    return status in {"listing_only", "partial", "failed"} or not record.get("lots")


def _mark_pending_shallow(record: dict[str, Any]) -> dict[str, Any]:
    pending = dict(record)
    pending["status"] = "listing_only"
    pending["parse_confidence"] = "minimal"
    warnings = list(pending.get("warnings") or [])
    if "deep_enrichment_pending" not in warnings:
        warnings.append("deep_enrichment_pending")
    pending["warnings"] = warnings
    pending["missing_fields"] = sorted(set((pending.get("missing_fields") or []) + ["lots"]))
    pending.setdefault("lots", [])
    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize a complete export from an incremental work plan.")
    parser.add_argument("--work-plan", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True, help="Export containing deep-parsed records")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-missing-deep-parse", action="store_true")
    parser.add_argument("--allow-small-output", action="store_true")
    args = parser.parse_args(argv)

    work_plan = load_work_plan(args.work_plan)
    previous = load_export(args.previous)
    parsed = load_export(args.parsed)
    output = materialize_incremental_export(
        work_plan=work_plan,
        previous_export=previous,
        parsed_export=parsed,
        discovery_export=None,
        allow_missing_deep_parse=args.allow_missing_deep_parse,
    )
    write_auctions_json(args.out, output, allow_small_output=args.allow_small_output)
    print(json.dumps(output["stats"]["incremental_materialize"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
