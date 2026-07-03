"""Deploy gem-reports/build to Hostinger (isolated from MSTC /auctions/)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUILD_DIR = REPO_ROOT / "gem-reports" / "build"
DEFAULT_REMOTE = (
    "/home/u268110164/domains/lightcyan-camel-979846.hostingersite.com/public_html/gem-reports"
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def deploy(build_dir: Path | None = None) -> None:
    source = build_dir or DEFAULT_BUILD_DIR
    if not source.is_dir() or not any(source.iterdir()):
        _log(f"ERROR: Build dir missing or empty: {source}")
        sys.exit(1)

    host = os.getenv("HOSTINGER_HOST", "82.25.107.163")
    port = os.getenv("HOSTINGER_PORT", "65002")
    user = os.getenv("HOSTINGER_USERNAME", "u268110164")
    key = os.path.expanduser(os.getenv("HOSTINGER_SSH_KEY", "~/.ssh/cursor_mstc_auction_hostinger"))
    remote = os.getenv("HOSTINGER_GEM_REPORTS_DIR", DEFAULT_REMOTE).strip()

    if not Path(key).is_file():
        _log(f"ERROR: SSH key not found: {key}")
        sys.exit(1)

    target = f"{user}@{host}"
    _log(f"Deploy gem-reports → {target}:{remote}")

    subprocess.run(
        ["ssh", "-i", key, "-p", port, "-o", "BatchMode=yes", target, f"mkdir -p {remote}"],
        check=True,
    )

    if shutil.which("rsync"):
        cmd = [
            "rsync", "-avz", "--delete",
            "-e", f"ssh -i {key} -p {port} -o BatchMode=yes",
            f"{source}/",
            f"{target}:{remote}/",
        ]
        subprocess.run(cmd, check=True)
    else:
        _log("rsync not found — using scp -r")
        subprocess.run(
            ["scp", "-i", key, "-P", port, "-r", str(source) + "/.", f"{target}:{remote}/"],
            check=True,
        )
    _log("Done: https://lightcyan-camel-979846.hostingersite.com/gem-reports/")


def main() -> int:
    deploy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
