"""Durable AI daily-usage ledger sync.

The local ledger still lives beside the AI cache, but scheduled runs can pull
and push the ledger to Hostinger so GitHub Actions cache misses do not reset
the daily OpenRouter budget.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scraper.ai_enrichment.queue import _ledger_path


@dataclass
class LedgerSyncResult:
    mode: str
    ok: bool
    action: str
    remote_path: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": self.mode,
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
        }
        if self.remote_path:
            payload["remote_path"] = self.remote_path
        return payload


def _required_env() -> dict[str, str]:
    values = {
        "HOSTINGER_HOST": os.environ.get("HOSTINGER_HOST", "").strip(),
        "HOSTINGER_PORT": os.environ.get("HOSTINGER_PORT", "").strip(),
        "HOSTINGER_USERNAME": os.environ.get("HOSTINGER_USERNAME", "").strip(),
        "HOSTINGER_SSH_KEY": os.environ.get("HOSTINGER_SSH_KEY", "").strip(),
        "HOSTINGER_REMOTE_DIR": os.environ.get("HOSTINGER_REMOTE_DIR", "").strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"missing Hostinger ledger env: {', '.join(missing)}")
    return values


def default_remote_ledger_path(remote_dir: str) -> str:
    """Return a private Hostinger path outside public_html when possible."""
    configured = os.environ.get("HOSTINGER_AI_LEDGER_PATH", "").strip()
    if configured:
        return configured

    marker = "/public_html/"
    if marker in remote_dir:
        domain_root = remote_dir.split(marker, 1)[0]
        return f"{domain_root}/ai_enrichment_state/_daily_usage.json"
    return f"{remote_dir.rstrip('/')}/.private/ai_enrichment/_daily_usage.json"


def _ssh_base(env: dict[str, str]) -> list[str]:
    return [
        "ssh",
        "-i",
        env["HOSTINGER_SSH_KEY"],
        "-p",
        env["HOSTINGER_PORT"],
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        f"{env['HOSTINGER_USERNAME']}@{env['HOSTINGER_HOST']}",
    ]


def _scp_base(env: dict[str, str]) -> list[str]:
    return [
        "scp",
        "-i",
        env["HOSTINGER_SSH_KEY"],
        "-P",
        env["HOSTINGER_PORT"],
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
    ]


def pull_remote_daily_usage(cache_dir: Path) -> LedgerSyncResult:
    """Pull today's ledger from Hostinger, creating an empty remote file if needed."""
    try:
        env = _required_env()
        remote_path = default_remote_ledger_path(env["HOSTINGER_REMOTE_DIR"])
        local_path = _ledger_path(cache_dir)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        remote_dir = remote_path.rsplit("/", 1)[0]
        target = f"{env['HOSTINGER_USERNAME']}@{env['HOSTINGER_HOST']}:{remote_path}"

        ensure_cmd = _ssh_base(env) + [
            f"mkdir -p {remote_dir} && test -f {remote_path} || printf '{{}}\\n' > {remote_path}"
        ]
        ensure = subprocess.run(ensure_cmd, capture_output=True, text=True, check=False)
        if ensure.returncode != 0:
            return LedgerSyncResult(
                mode="hostinger",
                ok=False,
                action="pull",
                remote_path=remote_path,
                message=(ensure.stderr or ensure.stdout or "remote ledger mkdir/read failed").strip(),
            )

        pull_cmd = _scp_base(env) + [target, str(local_path)]
        pulled = subprocess.run(pull_cmd, capture_output=True, text=True, check=False)
        if pulled.returncode != 0:
            return LedgerSyncResult(
                mode="hostinger",
                ok=False,
                action="pull",
                remote_path=remote_path,
                message=(pulled.stderr or pulled.stdout or "remote ledger pull failed").strip(),
            )
        return LedgerSyncResult(
            mode="hostinger",
            ok=True,
            action="pull",
            remote_path=remote_path,
            message="remote ledger pulled",
        )
    except Exception as exc:
        return LedgerSyncResult(mode="hostinger", ok=False, action="pull", message=str(exc))


def push_remote_daily_usage(cache_dir: Path) -> LedgerSyncResult:
    """Push the updated local ledger to Hostinger."""
    try:
        env = _required_env()
        remote_path = default_remote_ledger_path(env["HOSTINGER_REMOTE_DIR"])
        local_path = _ledger_path(cache_dir)
        if not local_path.is_file():
            return LedgerSyncResult(
                mode="hostinger",
                ok=False,
                action="push",
                remote_path=remote_path,
                message=f"local ledger missing: {local_path}",
            )
        remote_dir = remote_path.rsplit("/", 1)[0]
        target = f"{env['HOSTINGER_USERNAME']}@{env['HOSTINGER_HOST']}:{remote_path}"

        ensure_cmd = _ssh_base(env) + [f"mkdir -p {remote_dir}"]
        ensure = subprocess.run(ensure_cmd, capture_output=True, text=True, check=False)
        if ensure.returncode != 0:
            return LedgerSyncResult(
                mode="hostinger",
                ok=False,
                action="push",
                remote_path=remote_path,
                message=(ensure.stderr or ensure.stdout or "remote ledger mkdir failed").strip(),
            )

        push_cmd = _scp_base(env) + [str(local_path), target]
        pushed = subprocess.run(push_cmd, capture_output=True, text=True, check=False)
        if pushed.returncode != 0:
            return LedgerSyncResult(
                mode="hostinger",
                ok=False,
                action="push",
                remote_path=remote_path,
                message=(pushed.stderr or pushed.stdout or "remote ledger push failed").strip(),
            )
        return LedgerSyncResult(
            mode="hostinger",
            ok=True,
            action="push",
            remote_path=remote_path,
            message="remote ledger pushed",
        )
    except Exception as exc:
        return LedgerSyncResult(mode="hostinger", ok=False, action="push", message=str(exc))
