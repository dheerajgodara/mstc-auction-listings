"""Pipeline ledger v3 — mandatory portal PDF/doc → Hostinger → parse → deploy."""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, computed_field

from scraper.config import PDF_DETAIL_URL, REPO_ROOT, SITE_BASE_URL
from scraper.import_tracking import stable_auction_key
from scraper.incremental_queue import priority_score
from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, remote_pipeline_root

logger = logging.getLogger("scraper.pipeline_ledger")

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_LEDGER_PATH = REPO_ROOT / "work" / "pipeline_ledger.json"
StageStatus = Literal["pending", "done", "failed", "blocked"]
MAX_STAGE_ATTEMPTS = 5
LEDGER_SCHEMA_VERSION = 3
ACTIVE_SOURCES = frozenset({"mstc", "gem_forward"})


class LedgerItem(BaseModel):
    """v3 per-auction row. Unknown legacy keys discarded (extra=ignore)."""

    model_config = ConfigDict(extra="ignore")

    stable_key: str
    source: str
    source_auction_id: str

    portal_doc_url: Optional[str] = None
    hostinger_doc_url: Optional[str] = None
    hostinger_doc_path: Optional[str] = None
    doc_sha256: Optional[str] = None

    discover: StageStatus = "pending"
    download: StageStatus = "pending"
    parse: StageStatus = "pending"
    deploy: StageStatus = "pending"

    discover_attempts: int = 0
    download_attempts: int = 0
    parse_attempts: int = 0
    deploy_attempts: int = 0

    discover_error: Optional[str] = None
    download_error: Optional[str] = None
    parse_error: Optional[str] = None
    deploy_error: Optional[str] = None

    closing: Optional[str] = None
    opening: Optional[str] = None
    seller: Optional[str] = None
    state: Optional[str] = None
    detail_url: Optional[str] = None
    priority_score: int = 0

    lots_count: int = 0
    parsed_path: Optional[str] = None
    parsed_at: Optional[str] = None
    parser_version: Optional[str] = None

    raw_html_path: Optional[str] = None
    removed_from_source: bool = False
    first_seen_at: str = ""
    updated_at: str = ""
    deployed_at: Optional[str] = None

    # Compatibility aliases used by older telegram snippets / queue helpers
    @property
    def first_queued_at(self) -> str:
        return self.first_seen_at

    @property
    def last_error(self) -> Optional[str]:
        return self.parse_error or self.download_error or self.discover_error or self.deploy_error

    @computed_field  # type: ignore[prop-decorator]
    @property
    def publishable(self) -> bool:
        return compute_publishable(self)


class PipelineLedger(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generated_at: str
    items: list[LedgerItem] = Field(default_factory=list)
    version: int = LEDGER_SCHEMA_VERSION
    schema_version: int = LEDGER_SCHEMA_VERSION

    def by_key(self) -> dict[str, LedgerItem]:
        return {item.stable_key: item for item in self.items}

    def status_counts(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "discover": dict(Counter(i.discover for i in self.items)),
            "download": dict(Counter(i.download for i in self.items)),
            "parse": dict(Counter(i.parse for i in self.items)),
            "deploy": dict(Counter(i.deploy for i in self.items)),
            "publishable": sum(1 for i in self.items if compute_publishable(i)),
            "missing_portal_doc": sum(1 for i in self.items if not (i.portal_doc_url or "").strip()),
            "missing_hostinger_doc": sum(
                1 for i in self.items if not (i.hostinger_doc_url or "").strip()
            ),
            "removed_from_source": sum(1 for i in self.items if i.removed_from_source),
            "by_source": dict(Counter(i.source for i in self.items)),
            "total": len(self.items),
        }


def _now_iso() -> str:
    return datetime.now(IST).isoformat()


def empty_ledger() -> PipelineLedger:
    return PipelineLedger(
        generated_at=_now_iso(),
        items=[],
        version=LEDGER_SCHEMA_VERSION,
        schema_version=LEDGER_SCHEMA_VERSION,
    )


def compute_publishable(item: LedgerItem) -> bool:
    """True only when Hostinger doc exists and parse produced lots."""
    if item.removed_from_source:
        return False
    if item.source not in ACTIVE_SOURCES:
        return False
    if item.download != "done":
        return False
    if not (item.hostinger_doc_url or "").strip():
        return False
    if not (item.hostinger_doc_path or "").strip():
        return False
    if item.parse != "done":
        return False
    if int(item.lots_count or 0) <= 0:
        return False
    return True


def refresh_publishable(item: LedgerItem) -> LedgerItem:
    """No-op marker — publishable is computed; kept for call-site clarity."""
    _ = compute_publishable(item)
    return item


def public_doc_url(relative_path: str, *, site_base: str | None = None) -> str:
    base = (site_base if site_base is not None else SITE_BASE_URL or "").rstrip("/")
    rel = relative_path.lstrip("/")
    if not base:
        return rel
    return f"{base}/{rel}"


def mstc_portal_doc_url() -> str:
    return PDF_DETAIL_URL


def load_ledger(path: Path | None = None) -> PipelineLedger:
    path = Path(path or DEFAULT_LEDGER_PATH)
    if not path.is_file():
        return empty_ledger()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Coerce old version field
        if isinstance(raw, dict) and "schema_version" not in raw:
            raw["schema_version"] = int(raw.get("version") or 1)
        ledger = PipelineLedger.model_validate(raw)
        ledger.version = LEDGER_SCHEMA_VERSION
        ledger.schema_version = LEDGER_SCHEMA_VERSION
        return ledger
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("corrupt ledger at %s: %s; starting empty", path, exc)
        return empty_ledger()


def write_ledger(ledger: PipelineLedger, path: Path | None = None) -> Path:
    path = Path(path or DEFAULT_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger.generated_at = _now_iso()
    ledger.version = LEDGER_SCHEMA_VERSION
    ledger.schema_version = LEDGER_SCHEMA_VERSION
    path.write_text(ledger.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def patch_ledger_items(
    ledger: PipelineLedger,
    updates: dict[str, dict[str, Any]],
    *,
    allowed_fields: set[str] | frozenset[str] | None = None,
) -> PipelineLedger:
    by_key = ledger.by_key()
    now = _now_iso()
    for key, fields in updates.items():
        item = by_key.get(key)
        if item is None:
            continue
        for fname, value in fields.items():
            if allowed_fields is not None and fname not in allowed_fields:
                continue
            if hasattr(item, fname):
                setattr(item, fname, value)
        item.updated_at = now
        by_key[key] = item
    ledger.items = sorted(by_key.values(), key=lambda i: (-i.priority_score, i.stable_key))
    return ledger


def fail_budget_ok(*, failed: int, attempted: int, pct: float, absolute: int) -> bool:
    if attempted <= 0:
        return True
    return failed <= max(absolute, int(attempted * pct))


def _replace_item(ledger: PipelineLedger, item: LedgerItem) -> None:
    items = [i for i in ledger.items if i.stable_key != item.stable_key]
    items.append(item)
    ledger.items = sorted(items, key=lambda i: (-i.priority_score, i.stable_key))


def download_eligible(item: LedgerItem, *, source: str | None = None) -> bool:
    if item.removed_from_source:
        return False
    item_src = (item.source or "").strip().lower()
    src = (source or item_src).strip().lower()
    if item_src != src:
        return False
    if src not in ACTIVE_SOURCES:
        return False
    portal = (item.portal_doc_url or "").strip()
    if not portal and src == "mstc":
        # Catalogue endpoint is deterministic; heal empty portal from older rows.
        item.portal_doc_url = mstc_portal_doc_url()
        portal = item.portal_doc_url
    if not portal:
        return False
    if item.download in ("pending", "failed") and item.download_attempts < MAX_STAGE_ATTEMPTS:
        return True
    # Repair: marked done but missing Hostinger URL/path
    if item.download == "done" and (
        not (item.hostinger_doc_url or "").strip() or not (item.hostinger_doc_path or "").strip()
    ):
        return item.download_attempts < MAX_STAGE_ATTEMPTS
    return False


def mstc_download_eligible(item: LedgerItem) -> bool:
    return download_eligible(item, source="mstc")


def gem_download_eligible(item: LedgerItem) -> bool:
    return download_eligible(item, source="gem_forward")


def select_for_download(
    ledger: PipelineLedger,
    *,
    limit: int,
    pdf_dir: Path | None = None,
    source: str | None = None,
) -> list[LedgerItem]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    _ = pdf_dir
    src = (source or "mstc").strip().lower()
    eligible = [i for i in ledger.items if download_eligible(i, source=src)]
    eligible.sort(
        key=lambda i: (
            0 if i.download in ("pending", "failed") else 1,
            -i.priority_score,
            i.first_seen_at or "",
            i.stable_key,
        )
    )
    return eligible[:limit]


def classify_download_queue_item(item: LedgerItem) -> str:
    if item.download == "done" and not (item.hostinger_doc_url or "").strip():
        return "repair"
    if item.download in ("pending", "failed"):
        return "new"
    return "repair"


def select_for_parse(ledger: PipelineLedger, *, limit: int | None = None) -> list[LedgerItem]:
    eligible = [
        i
        for i in ledger.items
        if i.download == "done"
        and (i.hostinger_doc_url or "").strip()
        and (i.hostinger_doc_path or "").strip()
        and i.parse in ("pending", "failed")
        and i.parse_attempts < MAX_STAGE_ATTEMPTS
        and not i.removed_from_source
    ]
    eligible.sort(
        key=lambda i: (
            0 if i.source == "mstc" else 1,
            -i.priority_score,
            i.first_seen_at or "",
            i.stable_key,
        )
    )
    if limit is None:
        return eligible
    if limit <= 0:
        raise ValueError("limit must be positive")
    return eligible[:limit]


def select_publishable(ledger: PipelineLedger) -> list[LedgerItem]:
    return [i for i in ledger.items if compute_publishable(i) and not i.removed_from_source]


def upsert_from_work_plan(
    ledger: PipelineLedger,
    *,
    deep_items: list[Any],
    now: datetime | None = None,
    previous_export: dict[str, Any] | None = None,
    public_dir: Path | None = None,
    discovery_by_key: dict[str, dict[str, Any]] | None = None,
) -> PipelineLedger:
    """Merge discovery work-plan items; require portal_doc_url for active sources."""
    now = now or datetime.now(IST)
    by_key = ledger.by_key()
    previous_by_key = {
        stable_auction_key(a): a for a in (previous_export or {}).get("auctions", []) or []
    }
    discovery_by_key = discovery_by_key or {}

    for item in deep_items:
        key = getattr(item, "stable_key", None) or stable_auction_key(
            {
                "source": getattr(item, "source", "mstc"),
                "source_auction_id": getattr(item, "source_auction_id", None)
                or getattr(item, "id", None),
                "id": getattr(item, "id", None),
            }
        )
        source = str(getattr(item, "source", "mstc") or "mstc").strip().lower()
        aid = str(
            getattr(item, "source_auction_id", None)
            or (key.split(":", 1)[-1] if ":" in key else key)
        )
        if source not in ACTIVE_SOURCES:
            continue

        disc = discovery_by_key.get(key) or previous_by_key.get(key) or {}
        portal_doc = _resolve_portal_doc_url(source, aid, disc)
        existing = by_key.get(key)
        decision = str(getattr(item, "decision", None) or getattr(item, "action", "") or "")
        meta = getattr(item, "metadata", None) or {}
        closing = meta.get("closing") if isinstance(meta, dict) else disc.get("closing")
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

        if not portal_doc:
            # Discover fail — record row but do not queue download
            if existing is None:
                by_key[key] = LedgerItem(
                    stable_key=key,
                    source=source,
                    source_auction_id=aid,
                    discover="failed",
                    discover_attempts=1,
                    discover_error="missing portal_doc_url",
                    download="blocked",
                    parse="blocked",
                    deploy="blocked",
                    priority_score=priority,
                    closing=str(closing) if closing else None,
                    detail_url=str(disc.get("detail_url") or "") or None,
                    first_seen_at=now.isoformat(),
                    updated_at=now.isoformat(),
                )
            else:
                existing.discover = "failed"
                existing.discover_error = "missing portal_doc_url"
                existing.discover_attempts += 1
                existing.updated_at = now.isoformat()
                by_key[key] = existing
            continue

        listing_fields = dict(
            portal_doc_url=portal_doc,
            closing=str(closing) if closing else None,
            opening=str(disc.get("opening") or "") or None,
            seller=str(disc.get("seller") or "") or None,
            state=str(disc.get("state") or "") or None,
            detail_url=str(disc.get("detail_url") or "") or None,
            priority_score=priority,
        )

        if existing is None:
            by_key[key] = LedgerItem(
                stable_key=key,
                source=source,
                source_auction_id=aid,
                discover="done",
                download="pending",
                parse="pending",
                deploy="pending",
                first_seen_at=now.isoformat(),
                updated_at=now.isoformat(),
                **{k: v for k, v in listing_fields.items() if v is not None or k == "portal_doc_url"},
            )
            continue

        existing.discover = "done"
        existing.discover_error = None
        existing.portal_doc_url = portal_doc
        existing.removed_from_source = False
        existing.priority_score = max(existing.priority_score, priority)
        for fld in ("closing", "opening", "seller", "state", "detail_url"):
            val = listing_fields.get(fld)
            if val:
                setattr(existing, fld, val)
        if existing.download == "blocked" and existing.download_attempts < MAX_STAGE_ATTEMPTS:
            existing.download = "pending"
        if existing.parse == "blocked" and existing.parse_attempts < MAX_STAGE_ATTEMPTS:
            existing.parse = "pending"
        # Missing Hostinger doc → must download again
        if existing.download == "done" and not (existing.hostinger_doc_url or "").strip():
            existing.download = "pending"
        existing.updated_at = now.isoformat()
        by_key[key] = existing

    ledger.items = sorted(by_key.values(), key=lambda i: (-i.priority_score, i.stable_key))
    return ledger


def _resolve_portal_doc_url(source: str, aid: str, disc: dict[str, Any]) -> str | None:
    if source == "mstc":
        # Catalogue PDFs are fetched via POST auc=<id> to this endpoint.
        return mstc_portal_doc_url()
    if source == "gem_forward":
        for key in ("source_pdf_url", "pdf_url", "portal_doc_url"):
            v = disc.get(key)
            if isinstance(v, str) and v.strip() and "eauction-download-document" in v:
                return v.strip()
        docs = disc.get("document_urls") or []
        if isinstance(docs, list):
            for d in docs:
                if isinstance(d, str) and d.strip():
                    return d.strip()
                if isinstance(d, dict):
                    u = d.get("url") or d.get("href")
                    if isinstance(u, str) and u.strip():
                        return u.strip()
        return None
    return None


def mark_download(
    ledger: PipelineLedger,
    stable_key: str,
    *,
    ok: bool,
    hostinger_doc_path: str | None = None,
    hostinger_doc_url: str | None = None,
    doc_sha256: str | None = None,
    raw_html_path: str | None = None,
    error: str | None = None,
    content_changed: bool = True,
    # Legacy kwargs accepted but ignored (v3)
    pdf_path: str | None = None,
    require_media_resync: bool = True,
) -> LedgerItem | None:
    _ = require_media_resync
    item = ledger.by_key().get(stable_key)
    if item is None:
        return None
    item.download_attempts += 1
    item.updated_at = _now_iso()
    # Map legacy pdf_path arg
    if hostinger_doc_path is None and pdf_path:
        hostinger_doc_path = pdf_path
    if ok and hostinger_doc_path and not hostinger_doc_url:
        hostinger_doc_url = public_doc_url(hostinger_doc_path)

    if ok and hostinger_doc_path and hostinger_doc_url:
        item.download = "done"
        item.download_error = None
        item.hostinger_doc_path = hostinger_doc_path
        item.hostinger_doc_url = hostinger_doc_url
        if doc_sha256:
            item.doc_sha256 = doc_sha256
        if raw_html_path:
            item.raw_html_path = raw_html_path
        if content_changed:
            item.parse = "pending"
            item.lots_count = 0
            item.deploy = "pending"
    else:
        item.download_error = error or "download incomplete — hostinger doc required"
        item.hostinger_doc_path = None
        item.hostinger_doc_url = None
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
    lots_count: int = 0,
    parsed_path: str | None = None,
    error: str | None = None,
    parser_version: str | None = None,
    # Legacy
    deploy_ready: bool = False,
) -> LedgerItem | None:
    _ = deploy_ready
    item = ledger.by_key().get(stable_key)
    if item is None:
        return None
    item.parse_attempts += 1
    item.updated_at = _now_iso()
    if ok and int(lots_count) > 0:
        item.parse = "done"
        item.parse_error = None
        item.lots_count = int(lots_count)
        item.parsed_path = parsed_path
        item.parsed_at = _now_iso()
        if parser_version:
            item.parser_version = parser_version
        item.deploy = "pending"
    else:
        item.lots_count = 0
        item.parse_error = error or "no lots"
        if item.parse_attempts >= MAX_STAGE_ATTEMPTS:
            item.parse = "blocked"
        else:
            item.parse = "failed"
    _replace_item(ledger, item)
    return item


def mark_deploy(
    ledger: PipelineLedger,
    stable_key: str,
    *,
    ok: bool,
    error: str | None = None,
) -> LedgerItem | None:
    item = ledger.by_key().get(stable_key)
    if item is None:
        return None
    item.deploy_attempts += 1
    item.updated_at = _now_iso()
    if ok:
        item.deploy = "done"
        item.deploy_error = None
        item.deployed_at = _now_iso()
    else:
        item.deploy_error = error
        if item.deploy_attempts >= MAX_STAGE_ATTEMPTS:
            item.deploy = "blocked"
        else:
            item.deploy = "failed"
    _replace_item(ledger, item)
    return item


def estimated_download_runs_to_clear(
    ledger: PipelineLedger,
    *,
    cap: int,
    pdf_dir: Path | None = None,
    source: str | None = None,
) -> int:
    if cap <= 0:
        return 0
    pending = len(select_for_download(ledger, limit=10**9, pdf_dir=pdf_dir, source=source or "mstc"))
    if source is None:
        # Combined estimate across active sources
        pending = len(select_for_download(ledger, limit=10**9, source="mstc")) + len(
            select_for_download(ledger, limit=10**9, source="gem_forward")
        )
    if pending <= 0:
        return 0
    return int(math.ceil(pending / cap))


# --- Removed v2 helpers kept as no-ops for import safety ---


def grandfather_media_synced_legacy(ledger: PipelineLedger) -> int:
    _ = ledger
    return 0


def pull_ledger(
    *,
    local_path: Path | None = None,
    timeout_sec: int = 300,
    require: bool = False,
) -> bool:
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
    cmd = ["rsync", "-az", "-e", _ssh_cmd(cfg), remote, str(local)]
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
    cmd = ["rsync", "-az", "-e", _ssh_cmd(cfg), str(local), remote]
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec, capture_output=True, text=True)
        return True
    except Exception as exc:
        logger.warning("ledger push failed: %s", exc)
        return False
