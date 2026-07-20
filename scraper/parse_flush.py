"""Batch flush of parse artifacts to Hostinger (wave sync)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, remote_pipeline_root

logger = logging.getLogger("scraper.parse_flush")


def _ssh_base(cfg: dict) -> list[str]:
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
        f"ControlPath=/tmp/mstc_parse_ssh_%C",
        "-o",
        "ControlPersist=600",
    ]


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

    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False, "Hostinger SSH/rsync unavailable"

    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    ssh_e = (
        f"ssh -i {cfg['key_path']} -p {cfg['port']} "
        f"-o StrictHostKeyChecking=accept-new -o BatchMode=yes "
        f"-o ControlMaster=auto -o ControlPath=/tmp/mstc_parse_ssh_%C -o ControlPersist=600"
    )

    # Group by source for fewer rsync roots
    by_source: dict[str, list[Path]] = {}
    for f in files:
        try:
            rel = f.resolve().relative_to(Path(parsed_root).resolve())
        except ValueError:
            # Fallback: source = parent name
            rel = Path(f.parent.name) / f.name
        source = rel.parts[0] if rel.parts else "mstc"
        by_source.setdefault(source, []).append(f)

    uploaded = 0
    try:
        for source, paths in by_source.items():
            remote_dir = f"{remote_root}/parsed/{source}"
            mkdir = _ssh_base(cfg) + [target, f"mkdir -p {remote_dir}"]
            subprocess.run(mkdir, check=True, timeout=60, capture_output=True, text=True)
            # Stage into a temp dir preserving filenames then rsync the dir
            with tempfile.TemporaryDirectory(prefix="parse_flush_") as tmp:
                stage = Path(tmp)
                for p in paths:
                    dest = stage / p.name
                    shutil.copy2(p, dest)
                remote = f"{target}:{remote_dir}/"
                subprocess.run(
                    [
                        "rsync",
                        "-az",
                        "--compress-level=0",
                        "-e",
                        ssh_e,
                        f"{stage}/",
                        remote,
                    ],
                    check=True,
                    timeout=600,
                    capture_output=True,
                    text=True,
                )
                uploaded += len(paths)
        return True, f"flushed {uploaded} parsed file(s)"
    except Exception as exc:
        logger.warning("flush_parsed_files failed: %s", exc)
        return False, str(exc)
