"""Durable per-auction parse cache (Hostinger auction_pipeline/parsed/)."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import DEFAULT_PARSED_DIR, PARSER_CACHE_VERSION, REPO_ROOT
from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, remote_pipeline_root

logger = logging.getLogger("scraper.parse_cache")
IST = ZoneInfo("Asia/Kolkata")


def local_parsed_path(
    source: str,
    source_auction_id: str,
    *,
    root: Path | None = None,
) -> Path:
    root = Path(root or DEFAULT_PARSED_DIR)
    return root / source.strip() / f"{source_auction_id}.json"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_parse_artifact(
    *,
    record: dict[str, Any],
    stable_key: str,
    pdf_sha256: str | None = None,
    html_sha256: str | None = None,
    parser_version: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "meta": {
            "stable_key": stable_key,
            "pdf_sha256": pdf_sha256,
            "html_sha256": html_sha256,
            "parsed_at": datetime.now(IST).isoformat(),
            "parser_version": parser_version or PARSER_CACHE_VERSION,
        },
        "record": record,
    }


def write_parse_artifact(path: Path, artifact: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_parse_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_fresh_parse(
    artifact: dict[str, Any] | None,
    *,
    pdf_sha256: str | None,
    html_sha256: str | None = None,
    parser_version: str | None = None,
) -> bool:
    if not artifact:
        return False
    meta = artifact.get("meta") or {}
    if str(meta.get("parser_version") or "") != str(parser_version or PARSER_CACHE_VERSION):
        return False
    if pdf_sha256 and str(meta.get("pdf_sha256") or "") != pdf_sha256:
        return False
    if html_sha256 and meta.get("html_sha256") and str(meta.get("html_sha256")) != html_sha256:
        return False
    record = artifact.get("record") or {}
    lots = record.get("lots") if isinstance(record, dict) else None
    return isinstance(lots, list) and len(lots) > 0


def push_parsed_file(local_path: Path, *, source: str, source_auction_id: str) -> bool:
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None or not local_path.is_file():
        return False
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    remote_dir = f"{remote_root}/parsed/{source}"
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
        f"mkdir -p {remote_dir}",
    ]
    try:
        subprocess.run(mkdir_cmd, check=True, timeout=60, capture_output=True, text=True)
        remote = f"{target}:{remote_dir}/{source_auction_id}.json"
        subprocess.run(
            ["rsync", "-az", "-e", _ssh_cmd(cfg), str(local_path), remote],
            check=True,
            timeout=120,
            capture_output=True,
            text=True,
        )
        return True
    except Exception as exc:
        logger.warning("push parsed %s/%s failed: %s", source, source_auction_id, exc)
        return False


def pull_parsed_tree(*, local_root: Path | None = None) -> int:
    """Pull Hostinger parsed/ into local work/parsed. Returns file count estimate."""
    cfg = _hostinger_ssh_config()
    local_root = Path(local_root or DEFAULT_PARSED_DIR)
    if cfg is None or shutil.which("rsync") is None:
        return 0
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    local_root.mkdir(parents=True, exist_ok=True)
    remote = f"{target}:{remote_root}/parsed/"
    try:
        subprocess.run(
            ["rsync", "-az", "-e", _ssh_cmd(cfg), remote, str(local_root) + "/"],
            check=True,
            timeout=600,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        logger.info("pull parsed tree skipped/failed: %s", exc)
        return 0
    return sum(1 for _ in local_root.rglob("*.json"))


def iter_local_parsed(root: Path | None = None) -> list[Path]:
    root = Path(root or DEFAULT_PARSED_DIR)
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.json"))


def push_discovery_snapshot(local_path: Path, remote_name: str) -> bool:
    """Push discovery_mstc_latest.json / discovery_gem_latest.json to Hostinger."""
    from scraper.pipeline_markers import push_pipeline_json

    if not local_path.is_file():
        return False
    try:
        data = json.loads(local_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return push_pipeline_json(remote_name, data)
