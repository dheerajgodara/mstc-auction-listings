"""Repair poison GeM docs (HTML shells saved as docs/gem/*.bin).

Scans Hostinger docs/gem, deletes HTML/unknown-magic files, resets ledger
download=pending so Download-GeM re-fetches via file-list.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import subprocess
import sys
from pathlib import Path

from scraper.config import DEFAULT_PIPELINE_LEDGER
from scraper.gem_doc_validate import looks_like_gem_html_shell
from scraper.pipeline_ledger import load_ledger, mark_download, pull_ledger, push_ledger, write_ledger
from scraper.raw_store import _hostinger_ssh_config

logger = logging.getLogger("scraper.gem_doc_repair")

_OLE = bytes.fromhex("d0cf11e0")


def _ssh_run(cfg: dict[str, str], remote_script: str) -> str:
    target = f"{cfg['username']}@{cfg['host']}"
    cmd = [
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
        remote_script,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ssh failed")
    return result.stdout


def _classify_head(head: bytes, size: int) -> tuple[bool, str | None, str | None]:
    if size < 500:
        return False, None, "gem_doc_too_small"
    if looks_like_gem_html_shell(head):
        low = head[:8192].lower()
        if b"session expired" in low or b"session-expired" in low:
            return False, None, "gem_session_expired"
        return False, None, "gem_html_shell"
    if head.startswith(b"%PDF"):
        return True, "pdf", None
    if head[:2] == b"PK":
        return True, "docx", None
    if head[:4] == _OLE:
        return True, "doc", None
    return False, None, "gem_unknown_magic"


def scan_and_repair(
    *,
    ledger_path: Path,
    dry_run: bool = True,
    push: bool = False,
    pull: bool = True,
) -> dict:
    cfg = _hostinger_ssh_config()
    if cfg is None:
        raise RuntimeError("Hostinger SSH not configured")

    remote_docs = f"{cfg['remote_dir'].rstrip('/')}/docs/gem"
    listing = _ssh_run(
        cfg,
        f"mkdir -p {remote_docs}; ls -1 {remote_docs} 2>/dev/null || true",
    )
    names = [n.strip() for n in listing.splitlines() if n.strip()]
    poison: list[dict] = []
    ok_n = 0
    for name in names:
        remote_path = f"{remote_docs}/{name}"
        try:
            head_b64 = _ssh_run(
                cfg,
                f"head -c 8192 {remote_path} | base64 -w 0 2>/dev/null || "
                f"head -c 8192 {remote_path} | base64",
            ).strip()
            head = base64.b64decode(head_b64)
            size = int(_ssh_run(cfg, f"wc -c < {remote_path}").strip())
        except Exception as exc:
            poison.append({"file": name, "aid": Path(name).stem, "error": f"read_failed: {exc}"})
            continue
        ok, kind, err = _classify_head(head, size)
        if ok:
            ok_n += 1
            continue
        poison.append(
            {
                "file": name,
                "aid": Path(name).stem,
                "bytes": size,
                "error": err,
                "kind": kind,
            }
        )

    if pull:
        pull_ledger(local_path=ledger_path)
    ledger = load_ledger(ledger_path)
    reset_keys: list[str] = []
    deleted = 0
    for p in poison:
        aid = str(p.get("aid") or Path(str(p.get("file") or "")).stem)
        if not dry_run:
            rel = f"{remote_docs}/{p['file']}"
            try:
                _ssh_run(cfg, f"rm -f {rel}")
                deleted += 1
            except Exception as exc:
                p["delete_error"] = str(exc)
        for item in ledger.items:
            if item.source != "gem_forward":
                continue
            if str(item.source_auction_id) != aid:
                continue
            if not dry_run:
                mark_download(
                    ledger,
                    item.stable_key,
                    ok=False,
                    error=p.get("error") or "gem_html_shell",
                )
                item.download = "pending"
                item.hostinger_doc_path = None
                item.hostinger_doc_url = None
                item.doc_sha256 = None
            reset_keys.append(item.stable_key)

    if not dry_run:
        write_ledger(ledger, ledger_path)
        if push:
            push_ledger(local_path=ledger_path)

    return {
        "scanned": len(names),
        "ok": ok_n,
        "poison": len(poison),
        "deleted": deleted if not dry_run else 0,
        "ledger_reset": len(reset_keys) if not dry_run else 0,
        "dry_run": dry_run,
        "poison_files": poison[:50],
        "reset_keys_sample": reset_keys[:50],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair poison GeM docs/gem HTML shells")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_PIPELINE_LEDGER)
    parser.add_argument("--apply", action="store_true", help="Delete poison files + reset ledger")
    parser.add_argument("--push", action="store_true", help="Push ledger to Hostinger")
    parser.add_argument("--no-pull", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    report = scan_and_repair(
        ledger_path=args.ledger,
        dry_run=not args.apply,
        push=bool(args.push),
        pull=not args.no_pull,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
