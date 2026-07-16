"""Sync AI enrichment cache archives to Hostinger for deploy-time hydration."""

from __future__ import annotations

import os
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scraper.config import AI_ENRICHMENT_CACHE_DIR


@dataclass
class CacheSyncResult:
    mode: str
    ok: bool
    action: str
    remote_path: Optional[str] = None
    file_count: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": self.mode,
            "ok": self.ok,
            "action": self.action,
            "file_count": self.file_count,
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
        "HOSTINGER_SSH_KEY": os.path.expanduser(os.environ.get("HOSTINGER_SSH_KEY", "").strip()),
        "HOSTINGER_REMOTE_DIR": os.environ.get("HOSTINGER_REMOTE_DIR", "").strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"missing Hostinger cache env: {', '.join(missing)}")
    return values


def default_remote_cache_archive_path(remote_dir: str) -> str:
    configured = os.environ.get("HOSTINGER_AI_CACHE_ARCHIVE", "").strip()
    if configured:
        return configured

    marker = "/public_html/"
    if marker in remote_dir:
        domain_root = remote_dir.split(marker, 1)[0]
        return f"{domain_root}/ai_enrichment_state/cache.tar.gz"
    return f"{remote_dir.rstrip('/')}/.private/ai_enrichment/cache.tar.gz"


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


def _count_cache_files(cache_dir: Path) -> int:
    if not cache_dir.is_dir():
        return 0
    return sum(1 for path in cache_dir.rglob("*") if path.is_file())


def _archive_cache(cache_dir: Path, archive_path: Path) -> int:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_count = 0
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in sorted(cache_dir.rglob("*")):
            if not path.is_file():
                continue
            tar.add(path, arcname=path.relative_to(cache_dir).as_posix())
            file_count += 1
    return file_count


def _extract_cache(archive_path: Path, cache_dir: Path) -> int:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_count = 0
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            tar.extract(member, path=cache_dir)
            file_count += 1
    return file_count


def pull_remote_ai_cache(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> CacheSyncResult:
    """Pull durable AI enrichment cache archive from Hostinger."""
    try:
        env = _required_env()
        remote_archive = default_remote_cache_archive_path(env["HOSTINGER_REMOTE_DIR"])
        remote_dir = remote_archive.rsplit("/", 1)[0]
        cache_dir.mkdir(parents=True, exist_ok=True)

        ensure_cmd = _ssh_base(env) + [
            f"mkdir -p {remote_dir} && test -f {remote_archive} || exit 2"
        ]
        ensure = subprocess.run(ensure_cmd, capture_output=True, text=True, check=False)
        if ensure.returncode == 2:
            return CacheSyncResult(
                mode="hostinger",
                ok=True,
                action="pull",
                remote_path=remote_archive,
                file_count=_count_cache_files(cache_dir),
                message="remote AI cache archive not found; using local/GHA cache only",
            )
        if ensure.returncode != 0:
            return CacheSyncResult(
                mode="hostinger",
                ok=False,
                action="pull",
                remote_path=remote_archive,
                message=(ensure.stderr or ensure.stdout or "remote cache probe failed").strip(),
            )

        with tempfile.TemporaryDirectory() as tmp:
            local_archive = Path(tmp) / "cache.tar.gz"
            target = f"{env['HOSTINGER_USERNAME']}@{env['HOSTINGER_HOST']}:{remote_archive}"
            pull_cmd = _scp_base(env) + [target, str(local_archive)]
            pulled = subprocess.run(pull_cmd, capture_output=True, text=True, check=False)
            if pulled.returncode != 0:
                return CacheSyncResult(
                    mode="hostinger",
                    ok=False,
                    action="pull",
                    remote_path=remote_archive,
                    message=(pulled.stderr or pulled.stdout or "remote AI cache pull failed").strip(),
                )
            extracted = _extract_cache(local_archive, cache_dir)
        return CacheSyncResult(
            mode="hostinger",
            ok=True,
            action="pull",
            remote_path=remote_archive,
            file_count=extracted,
            message="remote AI cache pulled",
        )
    except Exception as exc:
        return CacheSyncResult(mode="hostinger", ok=False, action="pull", message=str(exc))


def push_remote_ai_cache(cache_dir: Path = AI_ENRICHMENT_CACHE_DIR) -> CacheSyncResult:
    """Push local AI enrichment cache archive to Hostinger."""
    try:
        env = _required_env()
        remote_archive = default_remote_cache_archive_path(env["HOSTINGER_REMOTE_DIR"])
        remote_dir = remote_archive.rsplit("/", 1)[0]
        if not cache_dir.is_dir() or _count_cache_files(cache_dir) == 0:
            return CacheSyncResult(
                mode="hostinger",
                ok=True,
                action="push",
                remote_path=remote_archive,
                file_count=0,
                message="local AI cache empty; push skipped",
            )

        with tempfile.TemporaryDirectory() as tmp:
            local_archive = Path(tmp) / "cache.tar.gz"
            archived = _archive_cache(cache_dir, local_archive)
            ensure_cmd = _ssh_base(env) + [f"mkdir -p {remote_dir}"]
            ensure = subprocess.run(ensure_cmd, capture_output=True, text=True, check=False)
            if ensure.returncode != 0:
                return CacheSyncResult(
                    mode="hostinger",
                    ok=False,
                    action="push",
                    remote_path=remote_archive,
                    message=(ensure.stderr or ensure.stdout or "remote cache mkdir failed").strip(),
                )
            target = f"{env['HOSTINGER_USERNAME']}@{env['HOSTINGER_HOST']}:{remote_archive}"
            push_cmd = _scp_base(env) + [str(local_archive), target]
            pushed = subprocess.run(push_cmd, capture_output=True, text=True, check=False)
            if pushed.returncode != 0:
                return CacheSyncResult(
                    mode="hostinger",
                    ok=False,
                    action="push",
                    remote_path=remote_archive,
                    message=(pushed.stderr or pushed.stdout or "remote AI cache push failed").strip(),
                )
        return CacheSyncResult(
            mode="hostinger",
            ok=True,
            action="push",
            remote_path=remote_archive,
            file_count=archived,
            message="remote AI cache pushed",
        )
    except Exception as exc:
        return CacheSyncResult(mode="hostinger", ok=False, action="push", message=str(exc))
