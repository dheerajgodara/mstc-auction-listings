"""Decide automatic Pipeline Discover retries after hard failure."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import PIPELINE_DOWNLOAD_AUTO_RETRIES_PER_SLOT, PIPELINE_DOWNLOAD_CAP_CATCHUP
from scraper.download_retry_controller import decide_retry
from scraper.pipeline_markers import pull_pipeline_json, push_pipeline_json
from scraper.telegram_reporter import send_action_card

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.discover_retry_controller")

DISCOVER_RETRY_STATE = "discover_retry_state.json"


def _dispatch_discover(*, queue_cap: int, retry_of: str | None) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN required to dispatch discover")
    if subprocess.run(["which", "gh"], capture_output=True).returncode == 0:
        cmd = [
            "gh",
            "workflow",
            "run",
            "pipeline-discover.yml",
            "-f",
            f"queue_cap={queue_cap}",
        ]
        if retry_of:
            cmd.extend(["-f", f"retry_of={retry_of}"])
        env = {**os.environ, "GH_TOKEN": token}
        subprocess.run(cmd, check=True, env=env)
        return

    url = f"https://api.github.com/repos/{repo}/actions/workflows/pipeline-discover.yml/dispatches"
    body = {
        "ref": os.environ.get("GITHUB_REF_NAME") or "main",
        "inputs": {
            "queue_cap": str(queue_cap),
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


def run_discover_retry_controller(
    *,
    failed_run_id: str | None = None,
    failed_run_url: str | None = None,
    queue_cap: int = PIPELINE_DOWNLOAD_CAP_CATCHUP,
    dry_run: bool = False,
    sleep_enabled: bool = True,
) -> dict[str, Any]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    state = pull_pipeline_json(DISCOVER_RETRY_STATE) or {}
    decision = decide_retry(state=state, max_retries=PIPELINE_DOWNLOAD_AUTO_RETRIES_PER_SLOT)
    payload: dict[str, Any] = {
        "pipeline": "discover_retry",
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
            push_pipeline_json(DISCOVER_RETRY_STATE, new_state)
        payload["status"] = "exhausted"
        payload["finished_at"] = datetime.now(IST).isoformat()
        send_action_card(
            "discover_mstc",
            "automatic retries used up",
            context="Next scheduled discover will try again",
            critical=True,
        )
        return payload

    new_state = {
        **decision.state,
        "last_failed_at": datetime.now(IST).isoformat(),
        "last_run_id": failed_run_id,
        "wait_minutes": decision.wait_minutes,
    }
    if not dry_run:
        push_pipeline_json(DISCOVER_RETRY_STATE, new_state)
    payload["status"] = "retry_scheduled"
    payload["wait_minutes"] = decision.wait_minutes
    payload["retry_attempt"] = decision.attempt
    send_action_card(
        "discover_mstc",
        f"will retry (attempt {decision.attempt})",
        context=f"Waiting {decision.wait_minutes} minutes",
    )

    if sleep_enabled and not dry_run and decision.wait_minutes > 0:
        logger.info("sleeping %s minutes before discover retry", decision.wait_minutes)
        time.sleep(decision.wait_minutes * 60)

    if not dry_run:
        _dispatch_discover(queue_cap=queue_cap, retry_of=failed_run_id)
    payload["status"] = "dispatched"
    payload["finished_at"] = datetime.now(IST).isoformat()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-retry failed Pipeline Discover")
    parser.add_argument("--failed-run-id", default=os.environ.get("FAILED_RUN_ID"))
    parser.add_argument("--failed-run-url", default=os.environ.get("FAILED_RUN_URL"))
    parser.add_argument("--queue-cap", type=int, default=PIPELINE_DOWNLOAD_CAP_CATCHUP)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-sleep", action="store_true")
    args = parser.parse_args(argv)
    run_discover_retry_controller(
        failed_run_id=args.failed_run_id,
        failed_run_url=args.failed_run_url,
        queue_cap=args.queue_cap,
        dry_run=args.dry_run,
        sleep_enabled=not args.no_sleep,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
