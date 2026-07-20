"""Batch flush of parse artifacts to Hostinger (wave sync)."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from scraper.hostinger_ssh import (
    clear_stale_control_sockets,
    hostinger_ssh_config,
    run_rsync_with_retries,
    run_ssh,
    rsync_timeout_args,
    ssh_e,
)
from scraper.raw_store import remote_pipeline_root

logger = logging.getLogger("scraper.parse_flush")

_CONTROL = "/tmp/mstc_parse_ssh_%C"


def flush_parsed_files(
    local_files: list[Path],
    *,
    parsed_root: Path,
) -> tuple[bool, str]:
    """Rsync a set of local parsed JSON files to Hostinger under parsed/.

    Files must live under parsed_root/{source}/{id}.json.
    """
    files = [Path(p) for p in local_files if Path(p).is_file()]
    if not files:
        return True, "nothing to flush"

    cfg = hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False, "Hostinger SSH/rsync unavailable"

    clear_stale_control_sockets(prefix="/tmp/mstc_parse_ssh_")

    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    ssh_e_str = ssh_e(cfg, multiplex=True, control_path=_CONTROL)

    by_source: dict[str, list[Path]] = {}
    for f in files:
        try:
            rel = f.resolve().relative_to(Path(parsed_root).resolve())
        except ValueError:
            rel = Path(f.parent.name) / f.name
        source = rel.parts[0] if rel.parts else "mstc"
        by_source.setdefault(source, []).append(f)

    uploaded = 0
    errors: list[str] = []
    for source, paths in by_source.items():
        remote_dir = f"{remote_root}/parsed/{source}"
        try:
            run_ssh(
                cfg,
                f"mkdir -p {remote_dir}",
                timeout_sec=60,
                multiplex=True,
                control_path=_CONTROL,
            )
            with tempfile.TemporaryDirectory(prefix="parse_flush_") as tmp:
                stage = Path(tmp)
                for p in paths:
                    dest = stage / p.name
                    shutil.copy2(p, dest)
                remote = f"{target}:{remote_dir}/"
                cmd = [
                    "rsync",
                    "-az",
                    "--compress-level=0",
                    *rsync_timeout_args(),
                    "-e",
                    ssh_e_str,
                    f"{stage}/",
                    remote,
                ]
                run_rsync_with_retries(
                    cmd,
                    timeout_sec=180,
                    label=f"parse-flush:{source}",
                    attempts=3,
                )
                uploaded += len(paths)
        except Exception as exc:
            logger.warning("flush_parsed_files source=%s failed: %s", source, exc)
            errors.append(f"{source}: {exc}")

    if uploaded == 0:
        return False, "; ".join(errors) or "flush failed"
    msg = f"flushed {uploaded} parsed file(s)"
    if errors:
        msg += f" (partial: {'; '.join(errors[:3])})"
    return True, msg
