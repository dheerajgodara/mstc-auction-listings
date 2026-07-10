from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional, Tuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from scraper.incremental_plan import IncrementalWorkPlan, WorkPlanItem

IST = ZoneInfo("Asia/Kolkata")

QueueStatus = Literal["pending", "in_progress", "failed_retry", "blocked", "done"]


class QueueItem(BaseModel):
    stable_key: str
    source: str
    source_auction_id: Optional[str] = None
    decision: str
    priority_score: int
    closing: Optional[str] = None
    first_queued_at: str
    last_attempted_at: Optional[str] = None
    attempt_count: int = 0
    status: QueueStatus = "pending"
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueueState(BaseModel):
    generated_at: str
    max_deep_scrape_per_run: int
    selected_count: int
    pending_after_selection: int
    estimated_runs_to_clear: int
    status_counts: dict[str, int]
    decision_counts: dict[str, int]
    by_source: dict[str, dict[str, int]]
    selected_keys: list[str]
    items: list[QueueItem]


def load_queue(path: Path, previous_export: Optional[dict[str, Any]] = None) -> Optional[QueueState]:
    if path.is_file():
        return QueueState.model_validate(json.loads(path.read_text(encoding="utf-8")))
    stats_queue = ((previous_export or {}).get("stats") or {}).get("incremental_queue_state")
    if isinstance(stats_queue, dict) and stats_queue.get("items") is not None:
        return QueueState.model_validate(stats_queue)
    return None


def write_queue(path: Path, state: QueueState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")


def apply_queue_limit(
    plan: IncrementalWorkPlan,
    *,
    queue_path: Path,
    max_deep_scrape_per_run: int,
    previous_export: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Tuple[IncrementalWorkPlan, QueueState]:
    if max_deep_scrape_per_run <= 0:
        raise ValueError("max_deep_scrape_per_run must be positive")

    now = now or datetime.now(IST)
    prior = load_queue(queue_path, previous_export=previous_export)
    prior_items = {item.stable_key: item for item in (prior.items if prior else [])}
    current_deep_items = [item for item in plan.items if item.action == "deep_parse"]
    current_deep_keys = {item.stable_key for item in current_deep_items}

    queue_items: list[QueueItem] = []
    for item in current_deep_items:
        old = prior_items.get(item.stable_key)
        if old and old.status != "done":
            first_queued_at = old.first_queued_at
            attempt_count = old.attempt_count
            last_attempted_at = old.last_attempted_at
            status: QueueStatus = old.status if old.status != "in_progress" else "failed_retry"
        else:
            first_queued_at = now.isoformat()
            attempt_count = 0
            last_attempted_at = None
            status = "pending"
        queue_items.append(
            QueueItem(
                stable_key=item.stable_key,
                source=item.source,
                source_auction_id=item.source_auction_id,
                decision=item.decision,
                priority_score=priority_score(item, now=now),
                closing=_as_text(item.metadata.get("closing")),
                first_queued_at=first_queued_at,
                last_attempted_at=last_attempted_at,
                attempt_count=attempt_count,
                status=status,
                reasons=item.reasons,
                metadata=item.metadata,
            )
        )

    due = [item for item in queue_items if item.status != "blocked" and retry_due(item, now)]
    due.sort(key=lambda item: (-item.priority_score, _closing_sort(item.closing), item.first_queued_at, item.stable_key))
    selected_keys = {item.stable_key for item in due[:max_deep_scrape_per_run]}

    updated_queue_items: list[QueueItem] = []
    for item in queue_items:
        if item.stable_key in selected_keys:
            item.status = "in_progress"
            item.last_attempted_at = now.isoformat()
            item.attempt_count += 1
        updated_queue_items.append(item)

    selected_plan_items: list[WorkPlanItem] = []
    for item in plan.items:
        if item.action == "deep_parse" and item.stable_key not in selected_keys:
            selected_plan_items.append(item.model_copy(update={"action": "reuse_discovery"}))
        else:
            selected_plan_items.append(item)

    limited = _recount_plan(plan.model_copy(update={"items": selected_plan_items}))
    state = build_queue_state(
        queue_items=updated_queue_items,
        selected_keys=sorted(selected_keys),
        max_deep_scrape_per_run=max_deep_scrape_per_run,
        now=now,
    )
    write_queue(queue_path, state)
    return limited, state


def finalize_queue_after_run(
    *,
    queue_path: Path,
    selected_keys: set[str],
    parsed_export: dict[str, Any],
    max_deep_scrape_per_run: int,
    previous_export: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> QueueState:
    now = now or datetime.now(IST)
    state = load_queue(queue_path, previous_export=previous_export)
    if not state:
        state = build_queue_state(
            queue_items=[],
            selected_keys=[],
            max_deep_scrape_per_run=max_deep_scrape_per_run,
            now=now,
        )
    parsed_keys = {
        f"{str(a.get('source') or 'mstc').strip().lower()}:{str(a.get('source_auction_id') or a.get('id') or '').strip()}"
        for a in parsed_export.get("auctions", [])
    }
    next_items: list[QueueItem] = []
    for item in state.items:
        if item.stable_key not in selected_keys:
            next_items.append(item)
            continue
        if item.stable_key in parsed_keys:
            item.status = "done"
        elif item.attempt_count >= 5:
            item.status = "blocked"
        else:
            item.status = "failed_retry"
        next_items.append(item)

    # Keep done items out of the active queue; their successful deep data is now in production.
    active = [item for item in next_items if item.status != "done"]
    final_state = build_queue_state(
        queue_items=active,
        selected_keys=sorted(selected_keys),
        max_deep_scrape_per_run=max_deep_scrape_per_run,
        now=now,
    )
    write_queue(queue_path, final_state)
    return final_state


def build_queue_state(
    *,
    queue_items: list[QueueItem],
    selected_keys: list[str],
    max_deep_scrape_per_run: int,
    now: datetime,
) -> QueueState:
    status_counts = Counter(item.status for item in queue_items)
    decision_counts = Counter(item.decision for item in queue_items)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for item in queue_items:
        by_source[item.source][item.status] += 1
        by_source[item.source][item.decision] += 1
    pending_after = sum(1 for item in queue_items if item.status in {"pending", "failed_retry", "in_progress"})
    return QueueState(
        generated_at=now.isoformat(),
        max_deep_scrape_per_run=max_deep_scrape_per_run,
        selected_count=len(selected_keys),
        pending_after_selection=pending_after,
        estimated_runs_to_clear=math.ceil(max(0, pending_after - len(selected_keys)) / max_deep_scrape_per_run),
        status_counts=dict(status_counts),
        decision_counts=dict(decision_counts),
        by_source={source: dict(counter) for source, counter in by_source.items()},
        selected_keys=selected_keys,
        items=sorted(queue_items, key=lambda item: (-item.priority_score, _closing_sort(item.closing), item.stable_key)),
    )


def priority_score(item: WorkPlanItem, *, now: datetime) -> int:
    score = 0
    closing = _parse_dt(item.metadata.get("closing"))
    if closing:
        hours = (closing - now).total_seconds() / 3600
        if hours <= 24:
            score += 500
        elif hours <= 72:
            score += 300
        elif hours <= 168:
            score += 100
    score += {"new": 90, "changed": 70, "needs_repair": 80}.get(item.decision, 0)
    score += {"mstc": 30, "gem_forward": 20, "eauction": 10}.get(item.source, 0)
    if item.reasons:
        score += 5
    return score


def retry_due(item: QueueItem, now: datetime) -> bool:
    if item.status in {"pending", "in_progress"}:
        return True
    if item.status == "blocked":
        return False
    if not item.last_attempted_at:
        return True
    last = _parse_dt(item.last_attempted_at)
    if not last:
        return True
    delay = timedelta(hours=0)
    if item.attempt_count >= 3:
        delay = timedelta(hours=24)
    elif item.attempt_count >= 2:
        delay = timedelta(hours=6)
    return now >= last + delay


def _recount_plan(plan: IncrementalWorkPlan) -> IncrementalWorkPlan:
    action_counts: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for item in plan.items:
        action_counts[item.action] += 1
        by_source[item.source][item.action] += 1
        by_source[item.source][item.decision] += 1
    return plan.model_copy(
        update={
            "action_counts": dict(action_counts),
            "by_source": {source: dict(counter) for source, counter in by_source.items()},
        }
    )


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _closing_sort(value: Optional[str]) -> str:
    return value or "9999-12-31T23:59:59+05:30"


def _as_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)
