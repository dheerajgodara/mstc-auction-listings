"""Unified Hostinger SSH / rsync transport — fail-fast timeouts and retries.

All pipeline lanes should build SSH/rsync commands via this module so ConnectTimeout,
ServerAlive, and rsync --timeout are consistent (Phase A resilience).
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from scraper.config import HOSTINGER_REMOTE_DIR, REPO_ROOT

logger = logging.getLogger("scraper.hostinger_ssh")

# Fail-fast defaults (overridable via env)
SSH_CONNECT_TIMEOUT = int(os.getenv("SSH_CONNECT_TIMEOUT", "15"))
SSH_SERVER_ALIVE_INTERVAL = int(os.getenv("SSH_SERVER_ALIVE_INTERVAL", "30"))
SSH_SERVER_ALIVE_COUNT_MAX = int(os.getenv("SSH_SERVER_ALIVE_COUNT_MAX", "3"))
RSYNC_IO_TIMEOUT = int(os.getenv("RSYNC_IO_TIMEOUT", "120"))
SSH_CONTROL_PERSIST = int(os.getenv("SSH_CONTROL_PERSIST", "120"))
SSH_CONTROL_PATH_TMPL = os.getenv("SSH_CONTROL_PATH_TMPL", "/tmp/mstc_ssh_%C")
SSH_PREFLIGHT_TIMEOUT = int(os.getenv("SSH_PREFLIGHT_TIMEOUT", "25"))


def hostinger_ssh_config() -> dict[str, str] | None:
    host = (os.environ.get("HOSTINGER_HOST") or "").strip()
    port = (os.environ.get("HOSTINGER_PORT") or "22").strip()
    username = (os.environ.get("HOSTINGER_USERNAME") or "").strip()
    key_path = os.path.expanduser((os.environ.get("HOSTINGER_SSH_KEY") or "").strip())
    remote_dir = (
        os.environ.get("HOSTINGER_REMOTE_DIR") or HOSTINGER_REMOTE_DIR or ""
    ).strip()
    if not all([host, username, key_path, remote_dir]):
        return None
    if not Path(key_path).is_file():
        return None
    return {
        "host": host,
        "port": port,
        "username": username,
        "key_path": key_path,
        "remote_dir": remote_dir.rstrip("/"),
    }


def ssh_base_opts(
    *,
    multiplex: bool = False,
    control_path: str | None = None,
) -> list[str]:
    """Common -o flags for ssh clients."""
    opts = [
        "StrictHostKeyChecking=accept-new",
        "BatchMode=yes",
        f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        f"ServerAliveInterval={SSH_SERVER_ALIVE_INTERVAL}",
        f"ServerAliveCountMax={SSH_SERVER_ALIVE_COUNT_MAX}",
        "TCPKeepAlive=yes",
    ]
    if multiplex:
        path = control_path or SSH_CONTROL_PATH_TMPL
        opts.extend(
            [
                "ControlMaster=auto",
                f"ControlPath={path}",
                f"ControlPersist={SSH_CONTROL_PERSIST}",
            ]
        )
    return opts


def ssh_argv(
    cfg: dict[str, str],
    *,
    multiplex: bool = False,
    control_path: str | None = None,
) -> list[str]:
    argv = [
        "ssh",
        "-i",
        cfg["key_path"],
        "-p",
        str(cfg["port"]),
    ]
    for o in ssh_base_opts(multiplex=multiplex, control_path=control_path):
        argv.extend(["-o", o])
    return argv


def ssh_e(
    cfg: dict[str, str],
    *,
    multiplex: bool = False,
    control_path: str | None = None,
) -> str:
    """Shell string for rsync -e."""
    parts = [
        f"ssh -i {cfg['key_path']} -p {cfg['port']}",
    ]
    for o in ssh_base_opts(multiplex=multiplex, control_path=control_path):
        parts.append(f"-o {o}")
    return " ".join(parts)


def rsync_timeout_args(*, io_timeout: int | None = None) -> list[str]:
    return [f"--timeout={int(io_timeout if io_timeout is not None else RSYNC_IO_TIMEOUT)}"]


def clear_stale_control_sockets(*, prefix: str = "/tmp/mstc_ssh_") -> int:
    """Remove stale ControlMaster sockets so hung muxes cannot block a new job."""
    removed = 0
    for path in glob.glob(f"{prefix}*"):
        try:
            os.unlink(path)
            removed += 1
        except OSError:
            continue
    if removed:
        logger.info("cleared %d stale SSH control socket(s) under %s*", removed, prefix)
    return removed


def is_transport_error(exc: BaseException) -> bool:
    """SSH exit 255 / connection failures are transport; retry with backoff."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return True
    if isinstance(exc, subprocess.CalledProcessError):
        code = int(exc.returncode or 0)
        if code == 255:
            return True
        msg = f"{exc.stderr or ''}{exc.stdout or ''}{exc}".lower()
        return any(
            s in msg
            for s in (
                "connection refused",
                "connection timed out",
                "connection reset",
                "broken pipe",
                "network is unreachable",
                "no route to host",
            )
        )
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "connection refused",
            "connection timed out",
            "connection reset",
            "broken pipe",
            "network is unreachable",
            "no route to host",
            "exit status 255",
            "returned non-zero exit status 255",
        )
    )


def preflight_hostinger(*, timeout_sec: int | None = None) -> tuple[bool, str]:
    """ssh echo — abort lanes early when Hostinger is unreachable (retry once on timeout)."""
    cfg = hostinger_ssh_config()
    if cfg is None:
        return False, "Hostinger SSH env incomplete"
    if shutil.which("ssh") is None:
        return False, "ssh binary missing"
    to = int(timeout_sec if timeout_sec is not None else SSH_PREFLIGHT_TIMEOUT)
    last_msg = ""
    for attempt in range(2):
        t0 = time.monotonic()
        target = f"{cfg['username']}@{cfg['host']}"
        cmd = ssh_argv(cfg, multiplex=False) + [target, "echo ok"]
        try:
            if shutil.which("timeout"):
                cmd = ["timeout", str(to + 2), *cmd]
            proc = subprocess.run(
                cmd,
                check=True,
                timeout=to + 5,
                capture_output=True,
                text=True,
            )
            ms = int((time.monotonic() - t0) * 1000)
            out = (proc.stdout or "").strip()
            if "ok" not in out.lower():
                last_msg = f"preflight unexpected output ({ms}ms): {out[:80]!r}"
                continue
            return True, f"preflight ok connect_ms={ms} attempt={attempt + 1}"
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            last_msg = f"preflight failed ({ms}ms): {exc}"
            # Retry once on OS timeout (124) / connect hang.
            if attempt == 0 and ("124" in str(exc) or "timed out" in str(exc).lower()):
                time.sleep(1.5)
                continue
            break
    return False, last_msg


def run_ssh(
    cfg: dict[str, str],
    remote_cmd: str,
    *,
    timeout_sec: int = 60,
    multiplex: bool = False,
    control_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    target = f"{cfg['username']}@{cfg['host']}"
    cmd = ssh_argv(cfg, multiplex=multiplex, control_path=control_path) + [
        target,
        remote_cmd,
    ]
    if shutil.which("timeout"):
        cmd = ["timeout", str(max(1, timeout_sec + 2)), *cmd]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            timeout=timeout_sec + 5,
            capture_output=True,
            text=True,
        )
        logger.info(
            "ssh ok connect_ms=%d cmd=%s",
            int((time.monotonic() - t0) * 1000),
            remote_cmd[:60],
        )
        return proc
    except Exception:
        logger.warning(
            "ssh fail after_ms=%d cmd=%s",
            int((time.monotonic() - t0) * 1000),
            remote_cmd[:60],
        )
        raise


def run_rsync_with_retries(
    cmd: list[str],
    *,
    timeout_sec: int,
    label: str,
    attempts: int = 3,
    input_text: str | None = None,
) -> None:
    """Run rsync with short backoff. Raises on final failure."""
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        t0 = time.monotonic()
        try:
            run_cmd = list(cmd)
            if shutil.which("timeout") and not (
                run_cmd and run_cmd[0] == "timeout"
            ):
                run_cmd = ["timeout", str(max(1, timeout_sec + 5)), *run_cmd]
            kwargs: dict[str, Any] = {
                "check": True,
                "timeout": timeout_sec + 10,
                "capture_output": True,
                "text": True,
            }
            if input_text is not None:
                kwargs["input"] = input_text
            subprocess.run(run_cmd, **kwargs)
            logger.info(
                "%s rsync ok attempt=%d transfer_ms=%d",
                label,
                attempt,
                int((time.monotonic() - t0) * 1000),
            )
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last_exc = exc
            logger.warning(
                "%s rsync attempt %d/%d failed after_ms=%d: %s",
                label,
                attempt,
                attempts,
                int((time.monotonic() - t0) * 1000),
                exc,
            )
            if attempt < attempts:
                time.sleep(min(2**attempt, 8))
    assert last_exc is not None
    raise last_exc


def push_heartbeat(
    payload: dict[str, Any],
    *,
    filename: str = "download_heartbeat.json",
) -> bool:
    """Best-effort write of lane heartbeat to Hostinger auction_pipeline/."""
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    cfg = hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False
    # Inline domain root (avoid circular import with raw_store)
    remote = cfg["remote_dir"].rstrip("/")
    marker = "/public_html/"
    if marker in remote:
        domain_root = remote.split(marker, 1)[0]
    else:
        domain_root = str(Path(remote).parent.parent) if remote else ""
    remote_root = f"{domain_root.rstrip('/')}/auction_pipeline"

    IST = ZoneInfo("Asia/Kolkata")
    body = dict(payload)
    body.setdefault("recorded_at", datetime.now(IST).isoformat())
    local = Path(REPO_ROOT) / "work" / filename
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(body, indent=2, default=str), encoding="utf-8")
    target = f"{cfg['username']}@{cfg['host']}"
    remote_path = f"{target}:{remote_root}/{filename}"
    cmd = [
        "rsync",
        "-az",
        *rsync_timeout_args(),
        "-e",
        ssh_e(cfg, multiplex=False),
        str(local),
        remote_path,
    ]
    try:
        run_rsync_with_retries(cmd, timeout_sec=30, label="heartbeat", attempts=2)
        return True
    except Exception as exc:
        logger.warning("heartbeat push failed: %s", exc)
        return False
