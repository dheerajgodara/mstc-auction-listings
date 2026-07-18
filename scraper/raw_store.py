"""Durable raw HTML (and related metadata) store for the 3-job pipeline.

Local mirror: work/raw/{source}/{id}.html
Hostinger SoR: {domain_root}/auction_pipeline/raw/… (private, not under public_html)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from scraper.config import HOSTINGER_REMOTE_DIR, REPO_ROOT

logger = logging.getLogger("scraper.raw_store")

DEFAULT_RAW_DIR = REPO_ROOT / "work" / "raw"


def domain_root_from_remote_dir(remote_dir: str | None = None) -> str:
    """Derive Hostinger domain root from auctions public_html path."""
    remote = (remote_dir or os.environ.get("HOSTINGER_REMOTE_DIR") or HOSTINGER_REMOTE_DIR or "").rstrip("/")
    marker = "/public_html/"
    if marker in remote:
        return remote.split(marker, 1)[0]
    # Fallback: parent of remote auctions dir
    return str(Path(remote).parent.parent) if remote else ""


def remote_pipeline_root(remote_dir: str | None = None) -> str:
    root = domain_root_from_remote_dir(remote_dir)
    return f"{root.rstrip('/')}/auction_pipeline"


def raw_html_rel_path(source: str, auction_id: str) -> str:
    src = (source or "mstc").strip().lower().replace("-", "_")
    aid = str(auction_id).strip()
    return f"raw/{src}/{aid}.html"


def local_raw_html_path(source: str, auction_id: str, *, raw_dir: Path | None = None) -> Path:
    base = Path(raw_dir or DEFAULT_RAW_DIR)
    return base / raw_html_rel_path(source, auction_id).removeprefix("raw/")


def save_raw_html(
    source: str,
    auction_id: str,
    html: str,
    *,
    raw_dir: Path | None = None,
) -> Path:
    path = local_raw_html_path(source, auction_id, raw_dir=raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def load_raw_html(
    source: str,
    auction_id: str,
    *,
    raw_dir: Path | None = None,
) -> str | None:
    path = local_raw_html_path(source, auction_id, raw_dir=raw_dir)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def has_raw_html(
    source: str,
    auction_id: str,
    *,
    raw_dir: Path | None = None,
) -> bool:
    return local_raw_html_path(source, auction_id, raw_dir=raw_dir).is_file()


@dataclass
class RawSyncResult:
    attempted: bool
    ok: bool
    message: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "ok": self.ok,
            "message": self.message,
            "warnings": list(self.warnings),
        }


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


def pull_raw_store(*, raw_dir: Path | None = None, timeout_sec: int = 600) -> RawSyncResult:
    """Rsync remote auction_pipeline/raw/ → local work/raw/."""
    local = Path(raw_dir or DEFAULT_RAW_DIR)
    local.mkdir(parents=True, exist_ok=True)
    cfg = _hostinger_ssh_config()
    if cfg is None:
        return RawSyncResult(False, False, "Hostinger SSH env incomplete; skip raw pull", ["raw pull skipped"])
    if shutil.which("rsync") is None:
        return RawSyncResult(False, False, "rsync unavailable; skip raw pull", ["raw pull skipped: no rsync"])

    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    remote = f"{target}:{remote_root}/raw/"
    cmd = [
        "rsync",
        "-az",
        "--ignore-existing",
        "-e",
        _ssh_cmd(cfg),
        remote,
        f"{local}/",
    ]
    logger.info("Pulling raw store: %s -> %s", remote, local)
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        # First run: remote may not exist yet
        msg = (exc.stderr or exc.stdout or str(exc)).strip()
        return RawSyncResult(True, False, f"raw pull failed: {msg[:300]}", [msg[:300]])
    except subprocess.TimeoutExpired:
        return RawSyncResult(True, False, "raw pull timed out", ["raw pull timed out"])
    return RawSyncResult(True, True, f"raw store pulled into {local}")


def pull_raw_files(
    items: list[tuple[str, str]],
    *,
    raw_dir: Path | None = None,
    timeout_sec: int = 300,
) -> RawSyncResult:
    """Pull only selected raw HTML files from Hostinger (source, auction_id pairs)."""
    wanted = [(str(s).strip().lower(), str(a).strip()) for s, a in items if s and a]
    if not wanted:
        return RawSyncResult(False, True, "no raw files requested")
    local = Path(raw_dir or DEFAULT_RAW_DIR)
    local.mkdir(parents=True, exist_ok=True)
    cfg = _hostinger_ssh_config()
    if cfg is None:
        return RawSyncResult(False, False, "Hostinger SSH env incomplete; skip raw pull", ["raw pull skipped"])
    if shutil.which("rsync") is None:
        return RawSyncResult(False, False, "rsync unavailable; skip raw pull", ["raw pull skipped: no rsync"])

    # Keep already-local files out of the transfer list.
    missing = [
        (src, aid)
        for src, aid in wanted
        if not local_raw_html_path(src, aid, raw_dir=local).is_file()
    ]
    if not missing:
        return RawSyncResult(False, True, f"all {len(wanted)} raw files already local")

    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    files_from = local / ".rsync_raw_files_from"
    files_from.write_text(
        "\n".join(f"{src}/{aid}.html" for src, aid in missing) + "\n",
        encoding="utf-8",
    )
    cmd = [
        "rsync",
        "-az",
        "--ignore-existing",
        "--files-from",
        str(files_from),
        "-e",
        _ssh_cmd(cfg),
        f"{target}:{remote_root}/raw/",
        f"{local}/",
    ]
    logger.info("Pulling %s selected raw HTML files", len(missing))
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or str(exc)).strip()
        return RawSyncResult(True, False, f"selective raw pull failed: {msg[:300]}", [msg[:300]])
    except subprocess.TimeoutExpired:
        return RawSyncResult(True, False, "selective raw pull timed out", ["selective raw pull timed out"])
    finally:
        try:
            files_from.unlink(missing_ok=True)
        except Exception:
            pass
    return RawSyncResult(True, True, f"pulled {len(missing)} raw HTML files")


def push_raw_store(*, raw_dir: Path | None = None, timeout_sec: int = 600) -> RawSyncResult:
    """Rsync local work/raw/ → remote auction_pipeline/raw/."""
    local = Path(raw_dir or DEFAULT_RAW_DIR)
    if not local.is_dir():
        return RawSyncResult(False, True, "no local raw dir to push")
    cfg = _hostinger_ssh_config()
    if cfg is None:
        return RawSyncResult(False, False, "Hostinger SSH env incomplete; skip raw push", ["raw push skipped"])
    if shutil.which("rsync") is None:
        return RawSyncResult(False, False, "rsync unavailable; skip raw push", ["raw push skipped: no rsync"])

    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    # Ensure remote dirs exist
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
        f"{target}",
        f"mkdir -p {remote_root}/raw",
    ]
    try:
        subprocess.run(mkdir_cmd, check=True, timeout=60, capture_output=True, text=True)
    except Exception as exc:
        return RawSyncResult(True, False, f"mkdir remote raw failed: {exc}", [str(exc)])

    remote = f"{target}:{remote_root}/raw/"
    cmd = [
        "rsync",
        "-az",
        "-e",
        _ssh_cmd(cfg),
        f"{local}/",
        remote,
    ]
    logger.info("Pushing raw store: %s -> %s", local, remote)
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or str(exc)).strip()
        return RawSyncResult(True, False, f"raw push failed: {msg[:300]}", [msg[:300]])
    except subprocess.TimeoutExpired:
        return RawSyncResult(True, False, "raw push timed out", ["raw push timed out"])
    return RawSyncResult(True, True, f"raw store pushed to {remote_root}/raw")


def push_public_media(*, public_dir: Path, timeout_sec: int = 900) -> RawSyncResult:
    """Push local pdfs/docs/thumbs to Hostinger auctions media dirs (no --delete)."""
    cfg = _hostinger_ssh_config()
    if cfg is None:
        return RawSyncResult(False, False, "Hostinger SSH incomplete; skip media push", ["media push skipped"])
    if shutil.which("rsync") is None:
        return RawSyncResult(False, False, "rsync unavailable", ["media push skipped"])

    target = f"{cfg['username']}@{cfg['host']}"
    warnings: list[str] = []
    for name in ("pdfs", "docs", "thumbs"):
        local = public_dir / name
        if not local.is_dir():
            continue
        remote = f"{target}:{cfg['remote_dir']}/{name}/"
        cmd = [
            "rsync",
            "-az",
            "-e",
            _ssh_cmd(cfg),
            f"{local}/",
            remote,
        ]
        logger.info("Pushing media %s -> %s", local, remote)
        try:
            subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            msg = (exc.stderr or exc.stdout or str(exc)).strip()
            warnings.append(f"{name}: {msg[:200]}")
        except subprocess.TimeoutExpired:
            warnings.append(f"{name}: timed out")
    if warnings:
        return RawSyncResult(True, False, "media push partial failure", warnings)
    return RawSyncResult(True, True, "media pushed")


def push_public_pdf_files(
    *,
    public_dir: Path,
    filenames: list[str],
    timeout_sec: int = 300,
) -> RawSyncResult:
    """Push specific catalogue PDF basenames to Hostinger ``pdfs/`` (no --delete).

    Used for mid-run flushes so Hostinger ``pdfs/`` count rises during a download
    job while the per-run auction cap stays unchanged.
    """
    names = sorted({Path(n).name for n in filenames if str(n).strip()})
    if not names:
        return RawSyncResult(False, True, "no PDF filenames to push")

    cfg = _hostinger_ssh_config()
    if cfg is None:
        return RawSyncResult(False, False, "Hostinger SSH incomplete; skip PDF push", ["pdf push skipped"])
    if shutil.which("rsync") is None:
        return RawSyncResult(False, False, "rsync unavailable", ["pdf push skipped"])

    local_pdfs = Path(public_dir) / "pdfs"
    existing = [n for n in names if (local_pdfs / n).is_file()]
    missing = [n for n in names if n not in existing]
    if not existing:
        return RawSyncResult(
            True,
            False,
            "PDF push failed: none of the requested files exist locally",
            [f"missing: {', '.join(missing[:10])}"],
        )

    target = f"{cfg['username']}@{cfg['host']}"
    remote = f"{target}:{cfg['remote_dir']}/pdfs/"
    # Relative paths from pdfs/ so rsync places files directly in remote pdfs/.
    files_from = "\n".join(existing) + "\n"
    cmd = [
        "rsync",
        "-az",
        "-e",
        _ssh_cmd(cfg),
        "--files-from=-",
        f"{local_pdfs}/",
        remote,
    ]
    logger.info("Pushing %d PDF file(s) -> %s", len(existing), remote)
    try:
        subprocess.run(
            cmd,
            input=files_from,
            check=True,
            timeout=timeout_sec,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or str(exc)).strip()
        return RawSyncResult(True, False, f"PDF push failed: {msg[:300]}", [msg[:300]])
    except subprocess.TimeoutExpired:
        return RawSyncResult(True, False, "PDF push timed out", ["PDF push timed out"])

    warnings = [f"missing local: {n}" for n in missing[:20]] if missing else []
    msg = f"pushed {len(existing)} PDF file(s)"
    if missing:
        msg += f" ({len(missing)} missing locally)"
    return RawSyncResult(True, True, msg, warnings)