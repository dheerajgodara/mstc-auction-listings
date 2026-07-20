"""Batch Hostinger flush + parallel HTTP-200 verify for download waves."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scraper.pdf_flush import verify_hostinger_doc_url
from scraper.pipeline_ledger import public_doc_url
from scraper.raw_store import _hostinger_ssh_config, rsync_mkpath_args

logger = logging.getLogger("scraper.download_flush")


def _ssh_e(cfg: dict[str, str]) -> str:
    return (
        f"ssh -i {cfg['key_path']} -p {cfg['port']} "
        f"-o StrictHostKeyChecking=accept-new -o BatchMode=yes "
        f"-o ControlMaster=auto -o ControlPath=/tmp/mstc_dl_ssh_%C -o ControlPersist=600"
    )


def _ssh_base(cfg: dict[str, str]) -> list[str]:
    return [
        "ssh",
        "-i",
        cfg["key_path"],
        "-p",
        cfg["port"],
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        "-o",
        "ControlMaster=auto",
        "-o",
        "ControlPath=/tmp/mstc_dl_ssh_%C",
        "-o",
        "ControlPersist=600",
    ]


def flush_download_files(
    items: list[dict[str, Any]],
    *,
    public_dir: Path,
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Rsync local docs to Hostinger, then verify public URLs.

    Each item dict needs: stable_key, hostinger_doc_path (e.g. pdfs/1.pdf),
    local_path (absolute Path or str).

    Returns (ok, message, verified_items) where verified_items passed HTTP 200.
    If rsync fails entirely, verified_items is empty and ok is False.
    """
    ready: list[dict[str, Any]] = []
    for raw in items:
        rel = str(raw.get("hostinger_doc_path") or "").strip().lstrip("/")
        local = Path(str(raw.get("local_path") or ""))
        if not rel or not local.is_file():
            continue
        # Fail closed: never flush GeM HTML shells / unknown magic to Hostinger.
        if rel.startswith("docs/gem/"):
            from scraper.gem_doc_validate import classify_local_gem_file

            ok, _kind, err = classify_local_gem_file(local)
            if not ok:
                logger.warning(
                    "skip flush %s — local file failed gem magic (%s)",
                    rel,
                    err,
                )
                continue
        ready.append({**raw, "hostinger_doc_path": rel, "local_path": local})

    if not ready:
        return True, "nothing to flush", []

    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False, "Hostinger SSH/rsync unavailable", []

    # Group by remote parent dir under auctions root
    by_remote: dict[str, list[dict[str, Any]]] = {}
    for it in ready:
        rel = it["hostinger_doc_path"]
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent in (".", ""):
            parent = "pdfs"
        by_remote.setdefault(parent, []).append(it)

    target = f"{cfg['username']}@{cfg['host']}"
    ssh_e = _ssh_e(cfg)
    uploaded = 0
    try:
        for parent, group in by_remote.items():
            remote_dir = f"{cfg['remote_dir'].rstrip('/')}/{parent}"
            mkdir = _ssh_base(cfg) + [target, f"mkdir -p {remote_dir}"]
            subprocess.run(mkdir, check=True, timeout=60, capture_output=True, text=True)
            with tempfile.TemporaryDirectory(prefix="dl_flush_") as tmp:
                stage = Path(tmp)
                for it in group:
                    dest = stage / Path(it["hostinger_doc_path"]).name
                    shutil.copy2(it["local_path"], dest)
                remote = f"{target}:{remote_dir}/"
                cmd = [
                    "rsync",
                    "-az",
                    "--compress-level=0",
                    "--chmod=F644",
                    *rsync_mkpath_args(),
                    "-e",
                    ssh_e,
                    f"{stage}/",
                    remote,
                ]
                subprocess.run(
                    cmd,
                    check=True,
                    timeout=600,
                    capture_output=True,
                    text=True,
                )
                uploaded += len(group)
    except Exception as exc:
        logger.warning("flush_download_files rsync failed: %s", exc)
        return False, str(exc), []

    # Parallel HTTP verify
    verified: list[dict[str, Any]] = []

    def _check(it: dict[str, Any]) -> dict[str, Any] | None:
        url = public_doc_url(it["hostinger_doc_path"])
        if verify_hostinger_doc_url(url):
            out = dict(it)
            out["hostinger_doc_url"] = url
            return out
        return None

    workers = min(16, max(1, len(ready)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_check, it): it for it in ready}
        for fut in as_completed(futs):
            got = fut.result()
            if got is not None:
                verified.append(got)

    if len(verified) < len(ready):
        msg = f"flushed {uploaded}; verified {len(verified)}/{len(ready)}"
        return True, msg, verified
    return True, f"flushed+verified {len(verified)}", verified
