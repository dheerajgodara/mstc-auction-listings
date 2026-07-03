from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_LOCK_PATH = Path("work/refresh.lock")


class RefreshLockError(RuntimeError):
    pass


@dataclass
class RefreshLock:
    path: Path
    run_id: str
    pid: int
    started_at: str
    host: str

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "pid": self.pid,
            "started_at": self.started_at,
            "host": self.host,
        }


def _read_lock(path: Path) -> RefreshLock | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not data.get("run_id"):
        return None
    return RefreshLock(
        path=path,
        run_id=str(data["run_id"]),
        pid=int(data.get("pid") or 0),
        started_at=str(data.get("started_at") or ""),
        host=str(data.get("host") or ""),
    )


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _lock_age_minutes(lock: RefreshLock) -> float | None:
    if not lock.started_at:
        return None
    try:
        started = datetime.fromisoformat(lock.started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=IST)
        now = datetime.now(IST)
        return (now - started).total_seconds() / 60.0
    except ValueError:
        return None


def acquire_refresh_lock(
    *,
    lock_path: Path,
    run_id: str,
    stale_minutes: int = 10,
    break_stale_lock: bool = False,
) -> RefreshLock:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_lock(lock_path)
    if existing:
        alive = _process_alive(existing.pid)
        age = _lock_age_minutes(existing)
        stale = age is not None and age >= stale_minutes
        if alive and not stale:
            raise RefreshLockError(
                f"Another refresh is running (run_id={existing.run_id}, pid={existing.pid}). "
                "Wait for it to finish or use --break-stale-lock if the lock is stale."
            )
        if alive and stale and not break_stale_lock:
            raise RefreshLockError(
                f"Refresh lock is stale ({age:.0f} min) but process {existing.pid} is still alive. "
                "Use --break-stale-lock to override."
            )
        if not alive and not stale and not break_stale_lock:
            raise RefreshLockError(
                f"Stale lock file exists (run_id={existing.run_id}, pid={existing.pid} not running). "
                "Use --break-stale-lock to take over."
            )

    lock = RefreshLock(
        path=lock_path,
        run_id=run_id,
        pid=os.getpid(),
        started_at=datetime.now(IST).isoformat(),
        host=socket.gethostname(),
    )
    lock_path.write_text(json.dumps(lock.to_dict(), indent=2), encoding="utf-8")
    return lock


def release_refresh_lock(lock_path: Path, *, run_id: str | None = None) -> None:
    existing = _read_lock(lock_path)
    if not existing:
        return
    if run_id and existing.run_id != run_id:
        return
    try:
        lock_path.unlink()
    except OSError:
        pass
