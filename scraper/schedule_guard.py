from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

TARGET_SLOTS_IST: tuple[tuple[int, int], ...] = tuple(
    (hour, 0) for hour in range(24)
)


def latest_slot_start(now: datetime) -> datetime:
    now_ist = now.astimezone(IST)
    candidates: list[datetime] = []
    for day_offset in (0, -1):
        day = now_ist.date() + timedelta(days=day_offset)
        for hour, minute in TARGET_SLOTS_IST:
            candidates.append(
                datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST),
            )
    past = [slot for slot in candidates if slot <= now_ist]
    if not past:
        return min(candidates)
    return max(past)


def parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def should_skip_for_existing_run(
    runs: list[dict[str, Any]],
    *,
    current_run_id: str,
    slot_start: datetime,
) -> tuple[bool, str]:
    slot_start_utc = slot_start.astimezone(ZoneInfo("UTC"))
    for run in runs:
        if str(run.get("id")) == str(current_run_id):
            continue
        status = run.get("status")
        if status in {"queued", "in_progress"}:
            return True, f"another run is already {status}: {run.get('id')}"

    for run in runs:
        if str(run.get("id")) == str(current_run_id):
            continue
        created_at = parse_github_time(run.get("created_at"))
        if created_at is None or created_at < slot_start_utc:
            continue
        conclusion = run.get("conclusion")
        status = run.get("status")
        if status == "completed" and conclusion == "success":
            return True, f"slot already completed successfully: {run.get('id')}"
    return False, "no successful/running run found for this slot"


def fetch_workflow_runs(*, repo: str, workflow: str, token: str, limit: int = 20) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return list(data.get("workflow_runs") or [])


def write_github_env(name: str, value: str) -> None:
    env_path = os.environ.get("GITHUB_ENV")
    if env_path:
        with open(env_path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard scheduled refresh backup ticks")
    parser.add_argument("--workflow", default="refresh-and-deploy.yml")
    parser.add_argument("--now", default=None, help="ISO timestamp override for tests/manual debugging")
    args = parser.parse_args(argv)

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name != "schedule":
        write_github_env("REFRESH_SHOULD_RUN", "true")
        print("manual/non-schedule run: proceed")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repo or not run_id or not token:
        write_github_env("REFRESH_SHOULD_RUN", "true")
        print("schedule guard missing GitHub context; proceed rather than miss a run")
        return 0

    now = parse_github_time(args.now) if args.now else datetime.now(IST)
    if now is None:
        now = datetime.now(IST)
    slot = latest_slot_start(now)
    runs = fetch_workflow_runs(repo=repo, workflow=args.workflow, token=token)
    skip, reason = should_skip_for_existing_run(runs, current_run_id=run_id, slot_start=slot)
    write_github_env("REFRESH_SLOT_IST", slot.isoformat())
    write_github_env("REFRESH_SHOULD_RUN", "false" if skip else "true")
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
