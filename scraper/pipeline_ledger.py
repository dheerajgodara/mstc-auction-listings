"""Per-auction stage ledger for Download / Parse / Deploy pipeline."""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from scraper.config import HOSTINGER_REMOTE_DIR, REPO_ROOT
from scraper.import_tracking import stable_auction_key
from scraper.incremental_queue import priority_score
from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, remote_pipeline_root

logger = logging.getLogger("scraper.pipeline_ledger")

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_LEDGER_PATH = REPO_ROOT / "work" / "pipeline_ledger.json"
StageStatus = Literal["pending", "done", "failed", "blocked"]
MAX_STAGE_ATTEMPTS = 5


class LedgerItem(BaseModel):
    stable_key: str
    source: str
    source_auction_id: str
    download: StageStatus = "pending"
    parse: StageStatus = "pending"
    deploy_ready: bool = False
    media_synced: Optional[bool] = None
    media_synced_at: Optional[str] = None
    download_attempts: int = 0
    parse_attempts: int = 0
    decision: Optional[str] = None
    priority_score: int = 0
    closing: Optional[str] = None
    raw_html_path: Optional[str] = None
    pdf_path: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    last_error: Optional[str] = None
    updated_at: str = ""
    first_queued_at: str = ""


class PipelineLedger(BaseModel):
    generated_at: str
    items: list[LedgerItem] = Field(default_factory=list)
    version: int = 1

    def by_key(self) -> dict[str, LedgerItem]:
        return {item.stable_key: item for item in self.items}

    def status_counts(self) -> dict[str, Any]:
        download = Counter(i.download for i in self.items)
        parse = Counter(i.parse for i in self.items)
        return {
            "download": dict(download),
            "parse": dict(parse),
            "deploy_ready": sum(1 for i in self.items if i.deploy_ready),
            "total": len(self.items),
        }


def _now_iso() -> str:
    return datetime.now(IST).isoformat()


def empty_ledger() -> PipelineLedger:
    return PipelineLedger(generated_at=_now_iso(), items=[])


def load_ledger(path: Path | None = None) -> PipelineLedger:
    path = Path(path or DEFAULT_LEDGER_PATH)
    if not path.is_file():
        return empty_ledger()
    try:
        return PipelineLedger.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("corrupt ledger at %s: %s; starting empty", path, exc)
        return empty_ledger()


def write_ledger(ledger: PipelineLedger, path: Path | None = None) -> Path:
    path = Path(path or DEFAULT_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger.generated_at = _now_iso()
    path.write_text(ledger.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def upsert_from_work_plan(
    ledger: PipelineLedger,
    *,
    deep_items: list[Any],
    now: datetime | None = None,
    previous_export: dict[str, Any] | None = None,
    public_dir: Path | None = None,
) -> PipelineLedger:
    """Merge incremental deep_parse work-plan items into the ledger."""
    now = now or datetime.now(IST)
    by_key = ledger.by_key()
    previous_by_key = {
        stable_auction_key(a): a for a in (previous_export or {}).get("auctions", []) or []
    }

    for item in deep_items:
        key = getattr(item, "stable_key", None) or stable_auction_key(
            {
                "source": getattr(item, "source", "mstc"),
                "source_auction_id": getattr(item, "source_auction_id", None)
                or getattr(item, "id", None),
                "id": getattr(item, "id", None),
            }
        )
        source = str(getattr(item, "source", "mstc") or "mstc")
        aid = str(
            getattr(item, "source_auction_id", None)
            or (key.split(":", 1)[-1] if ":" in key else key)
        )
        existing = by_key.get(key)
        decision = str(getattr(item, "decision", None) or getattr(item, "action", "") or "")
        meta = getattr(item, "metadata", None) or {}
        closing = meta.get("closing") if isinstance(meta, dict) else None
        reasons = list(getattr(item, "reasons", None) or [])
        try:
            priority = int(
                priority_score(
                    item,
                    now=now,
                    previous_record=previous_by_key.get(key),
                    public_dir=public_dir,
                )
            )
        except Exception:
            priority = {"new": 90, "changed": 70, "needs_repair": 80}.get(decision, 10)

        # GeM / eAuction have no raw-HTML download stage; mark download done so
        # they enter the parse queue without consuming the MSTC download cap.
        src_l = source.strip().lower()
        initial_download = "pending" if src_l == "mstc" else "done"

        if existing is None:
            by_key[key] = LedgerItem(
                stable_key=key,
                source=source,
                source_auction_id=aid,
                download=initial_download,
                parse="pending",
                deploy_ready=False,
                decision=decision or None,
                priority_score=priority,
                closing=str(closing) if closing else None,
                reasons=reasons,
                first_queued_at=now.isoformat(),
                updated_at=now.isoformat(),
            )
            continue

        existing.decision = decision or existing.decision
        existing.priority_score = max(existing.priority_score, priority)
        if closing:
            existing.closing = str(closing)
        if reasons:
            existing.reasons = reasons
        if src_l != "mstc" and existing.download == "pending":
            existing.download = "done"
        if existing.download == "blocked" and existing.download_attempts < MAX_STAGE_ATTEMPTS:
            existing.download = "pending" if src_l == "mstc" else "done"
        if existing.parse == "blocked" and existing.parse_attempts < MAX_STAGE_ATTEMPTS:
            existing.parse = "pending"
        existing.updated_at = now.isoformat()
        by_key[key] = existing

    ledger.items = sorted(by_key.values(), key=lambda i: (-i.priority_score, i.stable_key))
    return ledger


def select_for_download(
    ledger: PipelineLedger,
    *,
    limit: int,
    pdf_dir: Path | None = None,
) -> list[LedgerItem]:
    """Select MSTC auctions that still need raw HTML/PDF download.

    Also re-queues:
    - ``download=done`` rows missing a valid local catalogue PDF
    - ``download=done`` rows with ``media_synced is False`` (Hostinger flush pending)
    """
    if limit <= 0:
        raise ValueError("limit must be positive")

    eligible: list[LedgerItem] = []
    for i in ledger.items:
        if i.source != "mstc":
            continue
        # Local PDF missing/corrupt — must re-download from MSTC.
        if i.download == "done" and _mstc_needs_pdf(i, pdf_dir):
            eligible.append(i)
            continue
        # Local OK but Hostinger sync not confirmed — re-run ensure + mid-run flush.
        if i.download == "done" and i.media_synced is False:
            eligible.append(i)
            continue
        if i.download in ("pending", "failed") and i.download_attempts < MAX_STAGE_ATTEMPTS:
            eligible.append(i)
    eligible.sort(key=lambda i: (-i.priority_score, i.first_queued_at or "", i.stable_key))
    return eligible[:limit]


def _mstc_needs_pdf(item: LedgerItem, pdf_dir: Path | None) -> bool:
    from scraper.pdf_downloader import validate_pdf_file

    if not (item.pdf_path or "").strip():
        return True
    if pdf_dir is None:
        return False
    aid = str(item.source_auction_id or "").strip()
    if not aid:
        return True
    return not validate_pdf_file(Path(pdf_dir) / f"{aid}.pdf")


def select_for_parse(ledger: PipelineLedger, *, limit: int | None = None) -> list[LedgerItem]:
    """Select auctions ready to parse. Prefer MSTC (disk) before live GeM/eAuction."""
    eligible = [
        i
        for i in ledger.items
        if i.download == "done"
        and i.parse in ("pending", "failed")
        and i.parse_attempts < MAX_STAGE_ATTEMPTS
    ]
    eligible.sort(
        key=lambda i: (
            0 if i.source == "mstc" else 1,
            -i.priority_score,
            i.first_queued_at or "",
            i.stable_key,
        )
    )
    if limit is None:
        return eligible
    if limit <= 0:
        raise ValueError("limit must be positive")
    return eligible[:limit]


def mark_download(
    ledger: PipelineLedger,
    stable_key: str,
    *,
    ok: bool,
    raw_html_path: str | None = None,
    pdf_path: str | None = None,
    error: str | None = None,
) -> LedgerItem | None:
    item = ledger.by_key().get(stable_key)
    if item is None:
        return None
    item.download_attempts += 1
    item.updated_at = _now_iso()
    if ok:
        item.download = "done"
        item.last_error = None
        if raw_html_path:
            item.raw_html_path = raw_html_path
        # Always record PDF path on success (required for MSTC foolproof download).
        item.pdf_path = pdf_path
        if pdf_path:
            # Hostinger durability is confirmed only after mid-run / final flush.
            item.media_synced = False
            item.media_synced_at = None
        # Successful re-download implies parse should re-run.
        if item.parse == "done":
            item.parse = "pending"
            item.deploy_ready = False
        elif item.parse == "blocked" and item.parse_attempts < MAX_STAGE_ATTEMPTS:
            item.parse = "pending"
    else:
        item.last_error = error
        # Clear stale pdf_path when download fails PDF requirement.
        if pdf_path is None:
            item.pdf_path = None
        if item.download_attempts >= MAX_STAGE_ATTEMPTS:
            item.download = "blocked"
        else:
            item.download = "failed"
    _replace_item(ledger, item)
    return item


def mark_parse(
    ledger: PipelineLedger,
    stable_key: str,
    *,
    ok: bool,
    deploy_ready: bool = False,
    error: str | None = None,
) -> LedgerItem | None:
    item = ledger.by_key().get(stable_key)
    if item is None:
        return None
    item.parse_attempts += 1
    item.updated_at = _now_iso()
    if ok:
        item.parse = "done"
        item.deploy_ready = bool(deploy_ready)
        item.last_error = None
    else:
        item.deploy_ready = False
        item.last_error = error
        if item.parse_attempts >= MAX_STAGE_ATTEMPTS:
            item.parse = "blocked"
        else:
            item.parse = "failed"
    _replace_item(ledger, item)
    return item


def _replace_item(ledger: PipelineLedger, item: LedgerItem) -> None:
    items = [i for i in ledger.items if i.stable_key != item.stable_key]
    items.append(item)
    ledger.items = sorted(items, key=lambda i: (-i.priority_score, i.stable_key))


def estimated_download_runs_to_clear(
    ledger: PipelineLedger,
    *,
    cap: int,
    pdf_dir: Path | None = None,
) -> int:
    """Estimate download job runs left, including done-without-valid-PDF repairs."""
    if cap <= 0:
        return 0
    # Same eligibility as select_for_download, without applying the per-run cap.
    pending = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir))
    if pending <= 0:
        return 0
    return int(math.ceil(pending / cap))


def pull_ledger(
    *,
    local_path: Path | None = None,
    timeout_sec: int = 300,
    require: bool = False,
) -> bool:
    """Pull remote pipeline_ledger.json via rsync.

    Returns True on success. Returns False when remote sync is unavailable
    (no Hostinger config / no rsync) and ``require`` is False.

    When ``require`` is True, any failure raises RuntimeError with a
    ``ledger pull failed`` message (including rsync non-zero exits).
    """
    local = Path(local_path or DEFAULT_LEDGER_PATH)
    local.parent.mkdir(parents=True, exist_ok=True)
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        msg = "ledger pull failed: Hostinger SSH/rsync not configured"
        if require:
            raise RuntimeError(msg)
        return False
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    remote = f"{target}:{remote_root}/pipeline_ledger.json"
    cmd = [
        "rsync",
        "-az",
        "-e",
        _ssh_cmd(cfg),
        remote,
        str(local),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
        return True
    except Exception as exc:
        msg = f"ledger pull failed: {exc}"
        if require:
            logger.error(msg)
            raise RuntimeError(msg) from exc
        logger.info("ledger pull skipped/failed: %s", exc)
        return False


def push_ledger(*, local_path: Path | None = None, timeout_sec: int = 120) -> bool:
    local = Path(local_path or DEFAULT_LEDGER_PATH)
    if not local.is_file():
        return False
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
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
        f"mkdir -p {remote_root}",
    ]
    try:
        subprocess.run(mkdir_cmd, check=True, timeout=60, capture_output=True, text=True)
    except Exception as exc:
        logger.warning("ledger remote mkdir failed: %s", exc)
        return False
    remote = f"{target}:{remote_root}/pipeline_ledger.json"
    cmd = [
        "rsync",
        "-az",
        "-e",
        _ssh_cmd(cfg),
        str(local),
        remote,
    ]
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
        return True
    except Exception as exc:
        logger.warning("ledger push failed: %s", exc)
        return False
