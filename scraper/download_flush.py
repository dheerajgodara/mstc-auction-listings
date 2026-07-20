"""Batch Hostinger flush + parallel HTTP-200 verify for download waves."""

from __future__ import annotations

import logging
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scraper.hostinger_ssh import (
    clear_stale_control_sockets,
    hostinger_ssh_config,
    run_rsync_with_retries,
    run_ssh,
    rsync_timeout_args,
    ssh_e,
)
from scraper.pdf_flush import verify_hostinger_doc_url
from scraper.pipeline_ledger import public_doc_url
from scraper.raw_store import rsync_mkpath_args

logger = logging.getLogger("scraper.download_flush")

_CONTROL = "/tmp/mstc_dl_ssh_%C"


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
    Per-parent-dir flush: one parent failure does not discard already-uploaded parents.
    """
    del public_dir  # reserved for future local staging roots
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

    cfg = hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False, "Hostinger SSH/rsync unavailable", []

    clear_stale_control_sockets(prefix="/tmp/mstc_dl_ssh_")

    by_remote: dict[str, list[dict[str, Any]]] = {}
    for it in ready:
        rel = it["hostinger_doc_path"]
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent in (".", ""):
            parent = "pdfs"
        by_remote.setdefault(parent, []).append(it)

    target = f"{cfg['username']}@{cfg['host']}"
    ssh_e_str = ssh_e(cfg, multiplex=True, control_path=_CONTROL)
    uploaded_items: list[dict[str, Any]] = []
    errors: list[str] = []

    for parent, group in by_remote.items():
        remote_dir = f"{cfg['remote_dir'].rstrip('/')}/{parent}"
        try:
            run_ssh(
                cfg,
                f"mkdir -p {remote_dir}",
                timeout_sec=60,
                multiplex=True,
                control_path=_CONTROL,
            )
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
                    *rsync_timeout_args(),
                    *rsync_mkpath_args(),
                    "-e",
                    ssh_e_str,
                    f"{stage}/",
                    remote,
                ]
                run_rsync_with_retries(
                    cmd,
                    timeout_sec=180,
                    label=f"dl-flush:{parent}",
                    attempts=3,
                )
                uploaded_items.extend(group)
        except Exception as exc:
            logger.warning("flush_download_files parent=%s failed: %s", parent, exc)
            errors.append(f"{parent}: {exc}")

    if not uploaded_items:
        return False, "; ".join(errors) or "rsync failed", []

    verified: list[dict[str, Any]] = []

    def _check(it: dict[str, Any]) -> dict[str, Any] | None:
        url = public_doc_url(it["hostinger_doc_path"])
        if verify_hostinger_doc_url(url):
            out = dict(it)
            out["hostinger_doc_url"] = url
            return out
        return None

    workers = min(16, max(1, len(uploaded_items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_check, it): it for it in uploaded_items}
        for fut in as_completed(futs):
            got = fut.result()
            if got is not None:
                verified.append(got)

    msg = f"flushed {len(uploaded_items)}; verified {len(verified)}/{len(uploaded_items)}"
    if errors:
        msg += f" (partial errors: {'; '.join(errors[:3])})"
    return True, msg, verified
