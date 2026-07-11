from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from scraper.incremental import ChangeDecision, compare_exports, load_export

IST = ZoneInfo("Asia/Kolkata")

WorkAction = Literal["deep_parse", "reuse_previous", "reuse_discovery", "mark_removed"]


class WorkPlanItem(BaseModel):
    stable_key: str
    source: str
    source_auction_id: Optional[str] = None
    decision: str
    action: WorkAction
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncrementalWorkPlan(BaseModel):
    generated_at: str
    snapshot_scope: str = "listing"
    counts: dict[str, int]
    action_counts: dict[str, int]
    by_source: dict[str, dict[str, int]]
    items: list[WorkPlanItem]


def decision_to_action(decision: ChangeDecision) -> WorkAction:
    if decision.status == "unchanged":
        return "reuse_previous"
    if decision.status == "removed":
        return "mark_removed"
    return "deep_parse"


def build_work_plan(discovery_export: dict[str, Any], previous_export: dict[str, Any] | None) -> IncrementalWorkPlan:
    active_sources = _active_sources(discovery_export)
    complete_sources = _complete_sources(discovery_export, active_sources)
    scoped_previous = _filter_previous_to_active_sources(previous_export, active_sources)
    report = compare_exports(discovery_export, scoped_previous, scope="listing")
    discovery_by_key = _discovery_record_index(discovery_export)
    items: list[WorkPlanItem] = []
    action_counts: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = defaultdict(Counter)

    kept_decisions: list[ChangeDecision] = []
    for decision in report.decisions:
        discovery_record = discovery_by_key.get(decision.stable_key)
        carried_from_fallback = discovery_record is not None and _is_carried_forward_record(discovery_record)
        if decision.status == "removed" and decision.source not in complete_sources:
            continue
        if carried_from_fallback:
            action: WorkAction = "reuse_previous"
            decision_label = "unchanged"
            reasons = sorted(set([*decision.reasons, "source_fallback_carried_forward"]))
        else:
            action = decision_to_action(decision)
            decision_label = decision.status
            reasons = decision.reasons

        kept_decisions.append(decision.model_copy(update={"status": decision_label, "reasons": reasons}))
        action_counts[action] += 1
        by_source[decision.source][action] += 1
        by_source[decision.source][decision_label] += 1
        items.append(
            WorkPlanItem(
                stable_key=decision.stable_key,
                source=decision.source,
                source_auction_id=decision.source_auction_id,
                decision=decision_label,
                action=action,
                reasons=reasons,
                metadata=_work_item_metadata(discovery_record),
            )
        )
    decision_counts = _decision_counts(kept_decisions, report.counts)

    return IncrementalWorkPlan(
        generated_at=datetime.now(IST).isoformat(),
        counts=decision_counts,
        action_counts=dict(action_counts),
        by_source={source: dict(counter) for source, counter in by_source.items()},
        items=items,
    )


def _active_sources(discovery_export: dict[str, Any]) -> set[str]:
    source_stats = ((discovery_export.get("stats") or {}).get("source_stats") or {})
    sources = {str(source).strip().lower() for source in source_stats if str(source).strip()}
    if sources:
        return sources
    return {
        str(a.get("source") or "mstc").strip().lower()
        for a in discovery_export.get("auctions", [])
        if str(a.get("source") or "mstc").strip()
    }


def _complete_sources(discovery_export: dict[str, Any], active_sources: set[str]) -> set[str]:
    source_stats = ((discovery_export.get("stats") or {}).get("source_stats") or {})
    if not source_stats:
        return set(active_sources)
    complete: set[str] = set()
    for source in active_sources:
        stats = source_stats.get(source) or {}
        if stats.get("complete") is not False:
            complete.add(source)
    return complete


def _decision_counts(decisions: list[ChangeDecision], original_counts: dict[str, int]) -> dict[str, int]:
    counts: dict[str, int] = {status: 0 for status in ("new", "unchanged", "changed", "removed", "needs_repair")}
    for decision in decisions:
        counts[decision.status] = counts.get(decision.status, 0) + 1
    counts["total_current"] = int(original_counts.get("total_current", 0))
    counts["total_previous"] = int(original_counts.get("total_previous", 0))
    counts["total_decisions"] = len(decisions)
    return counts


def _filter_previous_to_active_sources(
    previous_export: dict[str, Any] | None,
    active_sources: set[str],
) -> dict[str, Any] | None:
    if not previous_export or not active_sources:
        return previous_export
    previous = dict(previous_export)
    previous["auctions"] = [
        auction
        for auction in previous_export.get("auctions", [])
        if str(auction.get("source") or "mstc").strip().lower() in active_sources
    ]
    previous["count"] = len(previous["auctions"])
    return previous


def write_work_plan(path: Path, plan: IncrementalWorkPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_work_plan(path: Path) -> IncrementalWorkPlan:
    return IncrementalWorkPlan.model_validate(json.loads(path.read_text(encoding="utf-8")))


def ids_by_source_for_action(plan: IncrementalWorkPlan, action: WorkAction) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for item in plan.items:
        if item.action == action and item.source_auction_id:
            grouped[item.source].add(item.source_auction_id)
    return dict(grouped)


def mstc_ids_by_office_for_action(plan: IncrementalWorkPlan, action: WorkAction) -> dict[str, set[str]]:
    from scraper.config import OFFICE_CODES

    grouped: dict[str, set[str]] = defaultdict(set)
    for item in plan.items:
        if item.action != action or item.source != "mstc" or not item.source_auction_id:
            continue
        region = str(item.metadata.get("region") or "").upper()
        raw_office = str(item.metadata.get("office") or "").upper()
        office = region if region in OFFICE_CODES else raw_office
        if office:
            grouped[office].add(item.source_auction_id)
    return dict(grouped)


def _discovery_record_index(discovery_export: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from scraper.incremental import stable_listing_key

    return {stable_listing_key(a): a for a in discovery_export.get("auctions", [])}


def _work_item_metadata(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    metadata: dict[str, Any] = {}
    for key in ("office", "region", "state", "closing", "auction_number"):
        if record.get(key) is not None:
            metadata[key] = record.get(key)
    return metadata


def _is_carried_forward_record(record: dict[str, Any]) -> bool:
    warnings = record.get("warnings") or []
    return any("carried forward from previous production" in str(w) for w in warnings)


def write_action_id_lists(out_dir: Path, plan: IncrementalWorkPlan) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()
    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for item in plan.items:
        if not item.source_auction_id:
            continue
        grouped[item.action][item.source].append(item.source_auction_id)

    summary: dict[str, dict[str, int]] = {}
    for action, by_source in grouped.items():
        summary[action] = {}
        for source, ids in by_source.items():
            ids = sorted(set(ids))
            summary[action][source] = len(ids)
            (out_dir / f"{action}_{source}.json").write_text(
                json.dumps(ids, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an incremental deep-work plan from shallow discovery.")
    parser.add_argument("--discovery", type=Path, required=True, help="Current shallow discovery export")
    parser.add_argument("--previous", type=Path, help="Previous production export")
    parser.add_argument("--out", type=Path, required=True, help="Work plan JSON")
    parser.add_argument("--ids-dir", type=Path, help="Optional directory for per-action source ID lists")
    args = parser.parse_args(argv)

    discovery = load_export(args.discovery)
    previous = load_export(args.previous) if args.previous and args.previous.is_file() else None
    plan = build_work_plan(discovery, previous)
    write_work_plan(args.out, plan)
    if args.ids_dir:
        write_action_id_lists(args.ids_dir, plan)
    print(json.dumps({"counts": plan.counts, "action_counts": plan.action_counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
