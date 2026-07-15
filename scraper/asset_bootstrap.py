"""Pull production media (pdfs/docs/thumbs) from Hostinger into web/public before build."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("scraper.asset_bootstrap")

ASSET_DIRS = ("pdfs", "docs", "thumbs")


@dataclass
class AssetBootstrapResult:
    attempted: bool
    ok: bool
    message: str
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "ok": self.ok,
            "message": self.message,
            "pdf_count": self.counts.get("pdfs", 0),
            "docs_count": self.counts.get("docs", 0),
            "thumbs_count": self.counts.get("thumbs", 0),
            "counts": dict(self.counts),
            "warnings": list(self.warnings),
        }


def _count_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def _hostinger_ssh_config() -> dict[str, str] | None:
    host = (os.environ.get("HOSTINGER_HOST") or "").strip()
    port = (os.environ.get("HOSTINGER_PORT") or "22").strip()
    username = (os.environ.get("HOSTINGER_USERNAME") or "").strip()
    key_path = os.path.expanduser((os.environ.get("HOSTINGER_SSH_KEY") or "").strip())
    remote_dir = (os.environ.get("HOSTINGER_REMOTE_DIR") or "").strip()
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


def _ssh_cmd(cfg: dict[str, str]) -> str:
    return (
        f"ssh -i {cfg['key_path']} -p {cfg['port']} "
        "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    )


def count_public_assets(public_dir: Path) -> dict[str, int]:
    return {name: _count_files(public_dir / name) for name in ASSET_DIRS}


def bootstrap_production_assets(
    *,
    public_dir: Path,
    timeout_sec: int = 600,
    dirs: tuple[str, ...] | list[str] | None = None,
) -> AssetBootstrapResult:
    """
    Rsync Hostinger pdfs/, docs/, thumbs/ into public_dir.

    Existing local files win on conflict (`--ignore-existing` after pulling into
    a temp merge is awkward; we pull with update-if-newer semantics via rsync
    default, then any newly scraped local files already present are kept by
    using --ignore-existing so local/newer scrape artifacts are not overwritten).

    dirs: optional subset of ASSET_DIRS (e.g. ("pdfs",) for parse catch-up).
    """
    public_dir = Path(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    before = count_public_assets(public_dir)
    pull_dirs = tuple(dirs) if dirs is not None else ASSET_DIRS
    for name in pull_dirs:
        if name not in ASSET_DIRS:
            raise ValueError(f"unknown asset dir: {name}")

    cfg = _hostinger_ssh_config()
    if cfg is None:
        return AssetBootstrapResult(
            attempted=False,
            ok=False,
            message="Hostinger SSH env incomplete; skipped asset bootstrap",
            counts=before,
            warnings=["asset bootstrap skipped: HOSTINGER_* env incomplete"],
        )

    if shutil.which("rsync") is None:
        return AssetBootstrapResult(
            attempted=False,
            ok=False,
            message="rsync unavailable; skipped asset bootstrap",
            counts=before,
            warnings=["asset bootstrap skipped: rsync not on PATH"],
        )

    target = f"{cfg['username']}@{cfg['host']}"
    ssh = _ssh_cmd(cfg)
    warnings: list[str] = []
    pulled_any = False

    for name in pull_dirs:
        local_dir = public_dir / name
        local_dir.mkdir(parents=True, exist_ok=True)
        remote = f"{target}:{cfg['remote_dir']}/{name}/"
        cmd = [
            "rsync",
            "-az",
            "--ignore-existing",
            "-e",
            ssh,
            remote,
            f"{local_dir}/",
        ]
        logger.info("Bootstrapping assets: %s -> %s", remote, local_dir)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "rsync failed").strip()
            # Missing remote dir is non-fatal (new env / empty thumbs).
            if "No such file or directory" in err or "failed to set times" in err:
                warnings.append(f"{name}: remote missing or empty ({err[:200]})")
                continue
            warnings.append(f"{name}: bootstrap failed ({err[:300]})")
            continue
        pulled_any = True

    after = count_public_assets(public_dir)
    ok = pulled_any or any(after[k] > 0 for k in ASSET_DIRS)
    message = (
        f"bootstrapped assets pdfs={after['pdfs']} docs={after['docs']} thumbs={after['thumbs']} "
        f"(before pdfs={before['pdfs']} docs={before['docs']} thumbs={before['thumbs']})"
    )
    return AssetBootstrapResult(
        attempted=True,
        ok=ok,
        message=message,
        counts=after,
        warnings=warnings,
    )
