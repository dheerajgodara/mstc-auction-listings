"""Hostinger auction_pipeline/*.json markers (retry state, last deploy fingerprint)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, remote_pipeline_root

logger = logging.getLogger("scraper.pipeline_markers")

DOWNLOAD_RETRY_STATE = "download_retry_state.json"
LAST_DEPLOY_MARKER = "last_deploy.json"


def pull_pipeline_json(name: str, *, timeout_sec: int = 120) -> dict[str, Any] | None:
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return None
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    remote = f"{target}:{remote_root}/{name}"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / name
        cmd = ["rsync", "-az", "-e", _ssh_cmd(cfg), remote, str(local)]
        try:
            subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
        except Exception as exc:
            logger.info("pull %s skipped/failed: %s", name, exc)
            return None
        if not local.is_file():
            return None
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None


def push_pipeline_json(name: str, data: dict[str, Any], *, timeout_sec: int = 120) -> bool:
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    mkdir_cmd = [
        "ssh",
        "-i",
        cfg["key_path"],
        "-p",
        cfg["port"],
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        target,
        f"mkdir -p {remote_root}",
    ]
    try:
        subprocess.run(mkdir_cmd, check=True, timeout=60, capture_output=True, text=True)
    except Exception as exc:
        logger.warning("mkdir for markers failed: %s", exc)
        return False
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / name
        local.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        remote = f"{target}:{remote_root}/{name}"
        cmd = ["rsync", "-az", "-e", _ssh_cmd(cfg), str(local), remote]
        try:
            subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
            return True
        except Exception as exc:
            logger.warning("push %s failed: %s", name, exc)
            return False


def reset_download_retry_state(*, slot_id: str | None = None) -> bool:
    return push_pipeline_json(
        DOWNLOAD_RETRY_STATE,
        {
            "slot_id": slot_id,
            "attempt": 0,
            "last_failed_at": None,
            "last_run_id": None,
            "status": "ok",
        },
    )
