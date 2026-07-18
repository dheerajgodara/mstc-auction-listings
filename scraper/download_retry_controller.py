"""Decide automatic Pipeline Download retries after hard failure (not wait full 6h)."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import PIPELINE_DOWNLOAD_AUTO_RETRIES_PER_SLOT, PIPELINE_DOWNLOAD_CAP_CATCHUP
from scraper.pipeline_markers import DOWNLOAD_RETRY_STATE, pull_pipeline_json, push_pipeline_json
from scraper.schedule_guard import latest_slot_start
from scraper.telegram_reporter import send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.download_retry_controller")

# Backoff minutes for auto re-dispatch attempts 1 and 2 within a slot.
RETRY_BACKOFF_MINUTES = (15, 45)


@dataclass
class RetryDecision:
    should_retry: bool
    attempt: int
    wait_minutes: int
    slot_id: str
    reason: str
    state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_retry": self.should_retry,
            "attempt": self.attempt,
            "wait_minutes": self.wait_minutes,
            "slot_id": self.slot_id,
            "reason": self.reason,
            "state": self.state,
        }


def slot_id_for(now: datetime | None = None) -> str:
    slot = latest_slot_start(now or datetime.now(IST))
    return slot.strftime("%Y-%m-%dT%H:%M%z")


def decide_retry(
    *,
    state: dict[str, Any] | None,
    now: datetime | None = None,
    max_retries: int = PIPELINE_DOWNLOAD_AUTO_RETRIES_PER_SLOT,
) -> RetryDecision:
    now = now or datetime.now(IST)
    slot = slot_id_for(now)
    state = dict(state or {})
    prev_slot = str(state.get("slot_id") or "")
    attempt = int(state.get("attempt") or 0)
    if prev_slot != slot:
        # New 6h slot — fresh retry budget.
        attempt = 0
    if attempt >= max_retries:
        return RetryDecision(
            should_retry=False,
            attempt=attempt,
            wait_minutes=0,
            slot_id=slot,
            reason="retries_exhausted_for_slot",
            state={**state, "slot_id": slot, "attempt": attempt},
        )
    next_attempt = attempt + 1
    wait = RETRY_BACKOFF_MINUTES[min(next_attempt - 1, len(RETRY_BACKOFF_MINUTES) - 1)]
    return RetryDecision(
        should_retry=True,
        attempt=next_attempt,
        wait_minutes=wait,
        slot_id=slot,
        reason="schedule_retry",
        state={
            **state,
            "slot_id": slot,
            "attempt": next_attempt,
            "status": "retry_scheduled",
        },
    )


def _dispatch_download(*, max_download: int, retry_of: str | None) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN required to dispatch download")
    # Prefer gh if available.
    batch_size = 25
    max_batches = max(1, int(math.ceil(max_download / batch_size)))
    if subprocess.run(["which", "gh"], capture_output=True).returncode == 0:
        cmd = [
            "gh",
            "workflow",
            "run",
            "pipeline-download.yml",
            "-f",
            f"batch_size={batch_size}",
            "-f",
            f"max_batches={max_batches}",
        ]
        if retry_of:
            cmd.extend(["-f", f"retry_of={retry_of}"])
        env = {**os.environ, "GH_TOKEN": token}
        subprocess.run(cmd, check=True, env=env)
        return

    url = f"https://api.github.com/repos/{repo}/actions/workflows/pipeline-download.yml/dispatches"
    body = {
        "ref": os.environ.get("GITHUB_REF_NAME") or "main",
        "inputs": {
            "batch_size": str(batch_size),
            "max_batches": str(max_batches),
            "retry_of": retry_of or "",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (204, 200):
            raise RuntimeError(f"workflow_dispatch HTTP {resp.status}")


def run_download_retry_controller(
    *,
    failed_run_id: str | None = None,
    failed_run_url: str | None = None,
    max_download: int = PIPELINE_DOWNLOAD_CAP_CATCHUP,
    dry_run: bool = False,
    sleep_enabled: bool = True,
) -> dict[str, Any]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    state = pull_pipeline_json(DOWNLOAD_RETRY_STATE) or {}
    decision = decide_retry(state=state)
    payload: dict[str, Any] = {
        "pipeline": "download_retry",
        "status": "running",
        "failed_run_id": failed_run_id,
        "github_run_url": failed_run_url,
        "decision": decision.to_dict(),
        "started_at": datetime.now(IST).isoformat(),
    }

    if not decision.should_retry:
        new_state = {
            **decision.state,
            "last_failed_at": datetime.now(IST).isoformat(),
            "last_run_id": failed_run_id,
            "status": "exhausted",
        }
        if not dry_run:
            push_pipeline_json(DOWNLOAD_RETRY_STATE, new_state)
        payload["status"] = "exhausted"
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_telegram_report(payload, event="download_retries_exhausted")
        return payload

    new_state = {
        **decision.state,
        "last_failed_at": datetime.now(IST).isoformat(),
        "last_run_id": failed_run_id,
        "wait_minutes": decision.wait_minutes,
    }
    if not dry_run:
        push_pipeline_json(DOWNLOAD_RETRY_STATE, new_state)
    payload["status"] = "retry_scheduled"
    payload["wait_minutes"] = decision.wait_minutes
    payload["retry_attempt"] = decision.attempt
    send_telegram_report(payload, event="download_retry_scheduled")

    if sleep_enabled and not dry_run and decision.wait_minutes > 0:
        logger.info("sleeping %s minutes before download retry", decision.wait_minutes)
        time.sleep(decision.wait_minutes * 60)

    if not dry_run:
        _dispatch_download(max_download=max_download, retry_of=failed_run_id)
    payload["status"] = "dispatched"
    payload["finished_at"] = datetime.now(IST).isoformat()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-retry failed Pipeline Download")
    parser.add_argument("--failed-run-id", default=os.environ.get("FAILED_RUN_ID"))
    parser.add_argument("--failed-run-url", default=os.environ.get("FAILED_RUN_URL"))
    parser.add_argument("--max-download", type=int, default=PIPELINE_DOWNLOAD_CAP_CATCHUP)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-sleep", action="store_true")
    args = parser.parse_args(argv)
    run_download_retry_controller(
        failed_run_id=args.failed_run_id,
        failed_run_url=args.failed_run_url,
        max_download=args.max_download,
        dry_run=args.dry_run,
        sleep_enabled=not args.no_sleep,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
