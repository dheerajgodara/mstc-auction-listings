"""Deploy static site build (web/out/) to Hostinger via SSH."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from scraper.safety_gates import is_capped_mstc_only_export

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUILD_DIR = REPO_ROOT / "web" / "out"

REQUIRED_ENV = (
    "HOSTINGER_HOST",
    "HOSTINGER_PORT",
    "HOSTINGER_USERNAME",
    "HOSTINGER_SSH_KEY",
    "HOSTINGER_REMOTE_DIR",
)


def _log(message: str) -> None:
    print(message, flush=True)


def _expand_path(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _load_config() -> dict[str, str]:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key, "").strip()]
    if missing:
        _log(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    config = {key: os.getenv(key, "").strip() for key in REQUIRED_ENV}
    remote_dir = config["HOSTINGER_REMOTE_DIR"]
    expected = "/home/u268110164/domains/scrapauctionindia.com/public_html/auctions"
    if remote_dir.rstrip("/") != expected:
        _log("ERROR: Refusing auction deploy to non-production Hostinger path.")
        _log(f"Expected HOSTINGER_REMOTE_DIR: {expected}")
        _log(f"Actual HOSTINGER_REMOTE_DIR:   {remote_dir}")
        _log("Production auction deploys must target scrapauctionindia.com only.")
        sys.exit(1)

    return config


def _validate_build_dir(build_dir: Path) -> None:
    if not build_dir.is_dir():
        _log(f"ERROR: Build directory not found: {build_dir}")
        _log("Run `cd web && npm run build` first to create the static export.")
        sys.exit(1)

    if not any(build_dir.iterdir()):
        _log(f"ERROR: Build directory is empty: {build_dir}")
        sys.exit(1)


class DeployValidationError(Exception):
    """Raised when static export fails deploy safety checks."""


def validate_deploy_export(build_dir: Path) -> tuple[int, dict[str, int]]:
    """Inspect web/out data before rsync/SFTP. Raises DeployValidationError on unsafe export."""
    json_path = build_dir / "data" / "auctions.json"
    if not json_path.is_file():
        raise DeployValidationError(f"missing deploy data file: {json_path}")

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeployValidationError(f"cannot parse deploy data file: {json_path}: {exc}") from exc

    auctions = data.get("auctions")
    if not isinstance(auctions, list):
        raise DeployValidationError("deploy data file missing auctions array")

    count = int(data.get("count", len(auctions)))
    if count != len(auctions):
        raise DeployValidationError(
            f"deploy data count mismatch: header={count} actual={len(auctions)}"
        )

    if count <= 1:
        raise DeployValidationError(f"refusing deploy: auction count is {count}")

    by_source = dict(Counter(a.get("source", "missing") for a in auctions))
    if is_capped_mstc_only_export(by_source, count):
        raise DeployValidationError(
            "Refusing to deploy capped MSTC-only export. "
            f"count={count}, by_source={by_source}. "
            "Use refresh-and-deploy.yml for production."
        )

    return count, by_source


def _validate_ssh_key(ssh_key: str) -> Path:
    key_path = _expand_path(ssh_key)
    if not key_path.is_file():
        _log(f"ERROR: SSH key not found: {ssh_key}")
        _log("Set HOSTINGER_SSH_KEY to the path of your private key file.")
        sys.exit(1)
    return key_path


def _ssh_target(username: str, host: str) -> str:
    return f"{username}@{host}"


def _ensure_remote_dir(
    key_path: Path,
    port: str,
    username: str,
    host: str,
    remote_dir: str,
) -> None:
    target = _ssh_target(username, host)
    cmd = [
        "ssh",
        "-i",
        str(key_path),
        "-p",
        port,
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        target,
        f"mkdir -p {remote_dir}",
    ]
    _log(f"Ensuring remote directory exists: {remote_dir}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        _log(f"ERROR: Failed to create remote directory on {target}")
        if stderr:
            _log(stderr)
        sys.exit(1)


def _rsync_available() -> bool:
    return shutil.which("rsync") is not None


def _deploy_rsync(
    key_path: Path,
    port: str,
    username: str,
    host: str,
    remote_dir: str,
    build_dir: Path,
) -> None:
    target = _ssh_target(username, host)
    ssh_cmd = (
        f"ssh -i {key_path} -p {port} "
        "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    )
    # Keep --delete for HTML/data/app files, but never wipe production media
    # when CI has a sparse/empty pdfs|docs|thumbs tree.
    cmd = [
        "rsync",
        "-avz",
        "--delete",
        "--filter=P pdfs/",
        "--filter=P docs/",
        "--filter=P thumbs/",
        "-e",
        ssh_cmd,
        f"{build_dir}/",
        f"{target}:{remote_dir}/",
    ]
    _log(
        f"Deploying with rsync to {target}:{remote_dir} "
        "(protecting remote pdfs/, docs/, thumbs/ from --delete)"
    )
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        _log("ERROR: rsync deployment failed.")
        sys.exit(1)


def _sftp_mkdir_p(sftp, remote_path: str) -> None:
    parts = [part for part in remote_path.split("/") if part]
    current = ""
    for part in parts:
        current = f"{current}/{part}"
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def _deploy_sftp(
    key_path: Path,
    port: str,
    username: str,
    host: str,
    remote_dir: str,
    build_dir: Path,
) -> None:
    try:
        import paramiko
    except ImportError as exc:
        _log("ERROR: rsync is unavailable and paramiko is not installed for SFTP fallback.")
        _log("Install paramiko (`pip install paramiko`) or ensure rsync is on PATH.")
        raise SystemExit(1) from exc

    target = _ssh_target(username, host)
    _log(f"Deploying with SFTP to {target}:{remote_dir}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=int(port),
            username=username,
            key_filename=str(key_path),
            look_for_keys=False,
            allow_agent=False,
            timeout=30,
        )
        sftp = client.open_sftp()
        try:
            _sftp_mkdir_p(sftp, remote_dir)
            file_count = 0
            for local_path in sorted(build_dir.rglob("*")):
                if local_path.is_dir():
                    continue
                relative = local_path.relative_to(build_dir).as_posix()
                remote_path = f"{remote_dir.rstrip('/')}/{relative}"
                remote_parent = "/".join(remote_path.split("/")[:-1])
                if remote_parent:
                    _sftp_mkdir_p(sftp, remote_parent)
                sftp.put(str(local_path), remote_path)
                file_count += 1
            _log(f"Uploaded {file_count} files via SFTP.")
        finally:
            sftp.close()
    except Exception as exc:
        _log(f"ERROR: SFTP deployment failed: {exc}")
        sys.exit(1)
    finally:
        client.close()


def deploy(build_dir: Path | None = None) -> None:
    config = _load_config()
    source = build_dir or DEFAULT_BUILD_DIR
    key_path = _validate_ssh_key(config["HOSTINGER_SSH_KEY"])
    _validate_build_dir(source)

    try:
        count, by_source = validate_deploy_export(source)
    except DeployValidationError as exc:
        _log(f"ERROR: {exc}")
        sys.exit(1)

    host = config["HOSTINGER_HOST"]
    port = config["HOSTINGER_PORT"]
    username = config["HOSTINGER_USERNAME"]
    remote_dir = config["HOSTINGER_REMOTE_DIR"]

    _log("Starting Hostinger deployment (SSH key auth only).")
    _log(f"Source: {source}")
    _log(f"Deploy export: {count} auctions, by_source={by_source}")
    _log(f"Target: {username}@{host}:{remote_dir}")

    _ensure_remote_dir(key_path, port, username, host, remote_dir)

    if _rsync_available():
        _deploy_rsync(key_path, port, username, host, remote_dir, source)
    else:
        _log("rsync not found; falling back to SFTP.")
        _deploy_sftp(key_path, port, username, host, remote_dir, source)

    _log("Deployment completed successfully.")


def main() -> int:
    try:
        deploy()
        return 0
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
