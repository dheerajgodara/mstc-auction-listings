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


def _github_auth() -> tuple[str, str] | None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo or not token:
        return None
    return repo, token


def workflow_in_progress(workflow_file: str) -> bool:
    """True when any in_progress/queued run exists for this workflow file."""
    auth = _github_auth()
    if auth is None:
        return False
    repo, token = auth
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs"
        f"?status=in_progress&per_page=5"
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        total = int(data.get("total_count") or 0)
        if total > 0:
            return True
        # Also treat queued as busy
        url_q = (
            f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs"
            f"?status=queued&per_page=5"
        )
        req_q = urllib.request.Request(
            url_q,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req_q, timeout=30) as resp:
            data_q = json.loads(resp.read().decode("utf-8"))
        return int(data_q.get("total_count") or 0) > 0
    except Exception as exc:
        logger.info("workflow_in_progress check failed for %s: %s", workflow_file, exc)
        return False


def dispatch_workflow(workflow_file: str, inputs: dict[str, str] | None = None) -> bool:
    auth = _github_auth()
    if auth is None:
        logger.warning("cannot dispatch %s: missing GITHUB_REPOSITORY/TOKEN", workflow_file)
        return False
    repo, token = auth
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


def kick_if_needed(
    workflow_file: str,
    *,
    reason: str,
    backlog: int,
    inputs: dict[str, str] | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Dispatch downstream lane when backlog > 0, debounced if already running."""
    if backlog <= 0:
        return False, "backlog_clear"
    if not force and workflow_in_progress(workflow_file):
        logger.info("skip kick %s reason=%s backlog=%s (already in_progress)", workflow_file, reason, backlog)
        return False, "already_in_progress"
    ok = dispatch_workflow(workflow_file, inputs=inputs)
    if ok:
        logger.info("kicked %s reason=%s backlog=%s", workflow_file, reason, backlog)
        return True, reason
    return False, "dispatch_failed"


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
