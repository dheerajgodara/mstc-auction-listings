from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.schedule_guard import fetch_workflow_runs, parse_github_time, should_skip_for_existing_run, write_github_env

IST = ZoneInfo("Asia/Kolkata")

AI_TARGET_SLOTS_IST: tuple[tuple[int, int], ...] = (
    (1, 5),
    (4, 5),
    (7, 5),
    (10, 5),
    (13, 5),
    (16, 5),
    (19, 5),
    (22, 5),
)


def latest_ai_slot_start(now: datetime) -> datetime:
    now_ist = now.astimezone(IST)
    candidates: list[datetime] = []
    for day_offset in (0, -1):
        day = now_ist.date() + timedelta(days=day_offset)
        for hour, minute in AI_TARGET_SLOTS_IST:
            candidates.append(datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST))
    past = [slot for slot in candidates if slot <= now_ist]
    if not past:
        return min(candidates)
    return max(past)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard scheduled AI enrichment backup ticks")
    parser.add_argument("--workflow", default="ai-enrichment.yml")
    parser.add_argument("--now", default=None, help="ISO timestamp override for tests/manual debugging")
    args = parser.parse_args(argv)

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name != "schedule":
        write_github_env("AI_SHOULD_RUN", "true")
        print("manual/non-schedule AI run: proceed")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repo or not run_id or not token:
        write_github_env("AI_SHOULD_RUN", "true")
        print("AI schedule guard missing GitHub context; proceed rather than miss a run")
        return 0

    now = parse_github_time(args.now) if args.now else datetime.now(IST)
    if now is None:
        now = datetime.now(IST)
    slot = latest_ai_slot_start(now)
    runs = fetch_workflow_runs(repo=repo, workflow=args.workflow, token=token)
    skip, reason = should_skip_for_existing_run(runs, current_run_id=run_id, slot_start=slot)
    write_github_env("AI_SLOT_IST", slot.isoformat())
    write_github_env("AI_SHOULD_RUN", "false" if skip else "true")
    print(
        json.dumps(
            {
                "event": event_name,
                "slot_ist": slot.isoformat(),
                "current_run_id": run_id,
                "should_run": not skip,
                "reason": reason,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
