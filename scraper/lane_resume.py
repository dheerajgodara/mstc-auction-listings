"""Self-resume helper: redispatch the same GitHub workflow when backlog remains."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from scraper.pipeline_markers import pull_pipeline_json, push_pipeline_json

logger = logging.getLogger("scraper.lane_resume")
IST = ZoneInfo("Asia/Kolkata")


def should_self_resume(
    *,
    backlog_left: int,
    failed: int,
    attempted: int,
    fail_budget_ok: bool,
    elapsed_min: float,
    timebox_min: int,
) -> tuple[bool, str]:
    if backlog_left <= 0:
        return False, "backlog_clear"
    if not fail_budget_ok:
        return False, "fail_budget_exceeded"
    if elapsed_min < max(30, timebox_min * 0.85):
        # Still have runtime; caller should keep looping in-process.
        return False, "continue_in_process"
    return True, "timebox_near_limit"


def dispatch_workflow(workflow_file: str, inputs: dict[str, str] | None = None) -> bool:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo or not token:
        logger.warning("cannot dispatch %s: missing GITHUB_REPOSITORY/TOKEN", workflow_file)
        return False
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
    payload = {"ref": os.environ.get("GITHUB_REF_NAME") or "main", "inputs": inputs or {}}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            ok = 200 <= getattr(resp, "status", 204) < 300 or resp.status == 204
            logger.info("dispatched %s status=%s", workflow_file, getattr(resp, "status", "?"))
            return ok
    except Exception as exc:
        logger.warning("dispatch %s failed: %s", workflow_file, exc)
        return False


def record_resume(lane: str, meta: dict[str, Any]) -> None:
    name = f"{lane}_resume.json"
    state = {
        "lane": lane,
        "recorded_at": datetime.now(IST).isoformat(),
        **meta,
    }
    push_pipeline_json(name, state)


def load_resume(lane: str) -> dict[str, Any] | None:
    return pull_pipeline_json(f"{lane}_resume.json")
