"""Pipeline ledger v3 — portal PDF/doc → R2 CDN → parse → deploy.

Media durability is R2 (`object_doc_url` on files.scrapauctionindia.com).
`hostinger_doc_path` remains the stable relative media key (pdfs/…, docs/…).
"""

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

from scraper.config import PDF_DETAIL_URL, REPO_ROOT, R2_PUBLIC_BASE_URL, SITE_BASE_URL
from scraper.import_tracking import stable_auction_key
from scraper.incremental_queue import priority_score
from scraper.raw_store import _hostinger_ssh_config, _ssh_cmd, remote_pipeline_root

logger = logging.getLogger("scraper.pipeline_ledger")

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_LEDGER_PATH = REPO_ROOT / "work" / "pipeline_ledger.json"
StageStatus = Literal["pending", "done", "failed", "blocked", "fetched_local"]
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
    # Relative media key under CDN (pdfs/…, docs/gem/…). Name kept for ledger compat.
    hostinger_doc_path: Optional[str] = None
    # Legacy absolute Hostinger URL — deprecated; prefer object_doc_url.
    hostinger_doc_url: Optional[str] = None
    doc_sha256: Optional[str] = None
    # Local staging path after portal fetch, before R2 publish.
    local_doc_path: Optional[str] = None
    # Canonical public CDN URL (R2 / files.scrapauctionindia.com).
    object_doc_url: Optional[str] = None

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
                1 for i in self.items if not media_doc_url(i)
            ),
            "missing_cdn_doc": sum(1 for i in self.items if not media_doc_url(i)),
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


def media_doc_url(item: LedgerItem) -> str:
    """Canonical public media URL: prefer R2 CDN, fall back to legacy Hostinger URL."""
    obj = (item.object_doc_url or "").strip()
    if obj:
        return obj
    legacy = (item.hostinger_doc_url or "").strip()
    if legacy:
        return legacy
    rel = (item.hostinger_doc_path or "").strip()
    if rel:
        return public_doc_url(rel)
    return ""


def media_doc_path(item: LedgerItem) -> str:
    """Relative media key (pdfs/… or docs/…)."""
    return (item.hostinger_doc_path or "").strip().lstrip("/")


def compute_publishable(item: LedgerItem) -> bool:
    """True when durable CDN doc exists and parse produced lots."""
    if item.removed_from_source:
        return False
    if item.source not in ACTIVE_SOURCES:
        return False
    if item.download != "done":
        return False
    if not media_doc_url(item):
        return False
    if not media_doc_path(item):
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
    """Build absolute media URL for a relative key.

    Prefers R2_PUBLIC_BASE_URL (files.scrapauctionindia.com). Explicit site_base
    overrides for callers that still need SITE_BASE_URL joins.
    """
    if site_base is not None:
        base = site_base.strip().rstrip("/")
    else:
        base = (R2_PUBLIC_BASE_URL or SITE_BASE_URL or "").strip().rstrip("/")
    rel = str(relative_path or "").strip().lstrip("/")
    if not rel:
        return base
    if not base:
        return rel
    # Never allow the known broken join: .../auctions + pdfs → .../auctionspdfs
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


# Stage ranks for concurrent-writer merge (VPS download + GHA parse share one ledger file).
_DOWNLOAD_STAGE_RANK: dict[str, int] = {
    "blocked": -1,
    "pending": 0,
    "failed": 1,
    "fetched_local": 2,
    "done": 3,
}
_PARSE_STAGE_RANK: dict[str, int] = {
    "blocked": -1,
    "pending": 0,
    "failed": 1,
    "fetched_local": 0,
    "done": 3,
}
_DEPLOY_STAGE_RANK: dict[str, int] = {
    "blocked": -1,
    "pending": 0,
    "failed": 1,
    "fetched_local": 0,
    "done": 3,
}


def _stage_rank(status: str | None, table: dict[str, int]) -> int:
    return table.get(str(status or "pending"), 0)


def _prefer_nonempty(a: str | None, b: str | None) -> str | None:
    aa = (a or "").strip()
    bb = (b or "").strip()
    return aa or bb or None


def _parse_done(item: LedgerItem) -> bool:
    return item.parse == "done" and int(item.lots_count or 0) > 0


def merge_ledger_item(ours: LedgerItem, theirs: LedgerItem) -> LedgerItem:
    """Monotonic merge of two views of the same auction.

    Critical: never let a stale download writer regress ``parse=done`` back to
    ``pending`` (that race emptied the site after a successful parse wave).
    """
    if ours.stable_key != theirs.stable_key:
        raise ValueError(f"stable_key mismatch: {ours.stable_key!r} vs {theirs.stable_key!r}")

    out = theirs.model_copy(deep=True)

    # --- download + media ---
    ours_dl = _stage_rank(ours.download, _DOWNLOAD_STAGE_RANK)
    theirs_dl = _stage_rank(out.download, _DOWNLOAD_STAGE_RANK)
    if ours_dl > theirs_dl or (
        ours_dl == theirs_dl and (ours.object_doc_url or "").strip() and not (out.object_doc_url or "").strip()
    ):
        out.download = ours.download
        out.download_error = ours.download_error
        out.download_attempts = max(int(ours.download_attempts or 0), int(out.download_attempts or 0))
        for fld in (
            "hostinger_doc_path",
            "hostinger_doc_url",
            "object_doc_url",
            "doc_sha256",
            "local_doc_path",
            "raw_html_path",
            "portal_doc_url",
        ):
            val = getattr(ours, fld)
            if val:
                setattr(out, fld, val)
    else:
        out.download_attempts = max(int(ours.download_attempts or 0), int(out.download_attempts or 0))
        for fld in (
            "hostinger_doc_path",
            "hostinger_doc_url",
            "object_doc_url",
            "doc_sha256",
            "local_doc_path",
            "raw_html_path",
            "portal_doc_url",
        ):
            setattr(out, fld, _prefer_nonempty(getattr(out, fld), getattr(ours, fld)))

    # --- parse (never regress done→pending unless real content change) ---
    ours_done = _parse_done(ours)
    theirs_done = _parse_done(out)
    ours_sha = (ours.doc_sha256 or "").strip()
    out_sha = (out.doc_sha256 or "").strip()
    content_changed = bool(ours_sha and out_sha and ours_sha != out_sha and ours.download == "done")

    if ours_done and theirs_done:
        if int(ours.lots_count or 0) >= int(out.lots_count or 0):
            out.parse = "done"
            out.lots_count = int(ours.lots_count or 0)
            out.parsed_path = ours.parsed_path or out.parsed_path
            out.parsed_at = ours.parsed_at or out.parsed_at
            out.parser_version = ours.parser_version or out.parser_version
            out.parse_error = None
        out.parse_attempts = max(int(ours.parse_attempts or 0), int(out.parse_attempts or 0))
    elif theirs_done and not ours_done:
        if content_changed:
            out.parse = ours.parse
            out.lots_count = int(ours.lots_count or 0)
            out.parsed_path = ours.parsed_path
            out.parsed_at = ours.parsed_at
            out.parser_version = ours.parser_version
            out.parse_error = ours.parse_error
            # Take the new download bytes that invalidated parse.
            if ours_sha:
                out.doc_sha256 = ours_sha
            for fld in (
                "hostinger_doc_path",
                "hostinger_doc_url",
                "object_doc_url",
                "local_doc_path",
            ):
                val = getattr(ours, fld)
                if val:
                    setattr(out, fld, val)
        # else keep theirs parse=done
        out.parse_attempts = max(int(ours.parse_attempts or 0), int(out.parse_attempts or 0))
    elif ours_done and not theirs_done:
        out.parse = "done"
        out.lots_count = int(ours.lots_count or 0)
        out.parsed_path = ours.parsed_path
        out.parsed_at = ours.parsed_at
        out.parser_version = ours.parser_version
        out.parse_error = None
        out.parse_attempts = max(int(ours.parse_attempts or 0), int(out.parse_attempts or 0))
    else:
        if _stage_rank(ours.parse, _PARSE_STAGE_RANK) > _stage_rank(out.parse, _PARSE_STAGE_RANK):
            out.parse = ours.parse
            out.lots_count = int(ours.lots_count or 0)
            out.parsed_path = ours.parsed_path
            out.parsed_at = ours.parsed_at
            out.parser_version = ours.parser_version
            out.parse_error = ours.parse_error
        out.parse_attempts = max(int(ours.parse_attempts or 0), int(out.parse_attempts or 0))

    # --- deploy ---
    if _stage_rank(ours.deploy, _DEPLOY_STAGE_RANK) > _stage_rank(out.deploy, _DEPLOY_STAGE_RANK):
        out.deploy = ours.deploy
        out.deploy_error = ours.deploy_error
        out.deployed_at = ours.deployed_at or out.deployed_at
    out.deploy_attempts = max(int(ours.deploy_attempts or 0), int(out.deploy_attempts or 0))

    # --- discover + listing fields ---
    if _stage_rank(ours.discover, _DOWNLOAD_STAGE_RANK) > _stage_rank(out.discover, _DOWNLOAD_STAGE_RANK):
        out.discover = ours.discover
        out.discover_error = ours.discover_error
    out.discover_attempts = max(int(ours.discover_attempts or 0), int(out.discover_attempts or 0))
    for fld in ("closing", "opening", "seller", "state", "detail_url"):
        setattr(out, fld, _prefer_nonempty(getattr(out, fld), getattr(ours, fld)))
    out.priority_score = max(int(ours.priority_score or 0), int(out.priority_score or 0))
    out.removed_from_source = bool(ours.removed_from_source or out.removed_from_source)
    out.first_seen_at = min(
        x for x in (ours.first_seen_at or "", out.first_seen_at or "") if x
    ) or out.first_seen_at
    out.updated_at = max(ours.updated_at or "", out.updated_at or "") or _now_iso()
    return out


def merge_ledgers(ours: PipelineLedger, theirs: PipelineLedger) -> PipelineLedger:
    """Union merge by stable_key — keeps progress from both concurrent writers."""
    by: dict[str, LedgerItem] = {i.stable_key: i.model_copy(deep=True) for i in theirs.items}
    for item in ours.items:
        existing = by.get(item.stable_key)
        if existing is None:
            by[item.stable_key] = item.model_copy(deep=True)
        else:
            by[item.stable_key] = merge_ledger_item(item, existing)
    return PipelineLedger(
        generated_at=_now_iso(),
        items=sorted(by.values(), key=lambda i: i.stable_key),
        version=LEDGER_SCHEMA_VERSION,
        schema_version=LEDGER_SCHEMA_VERSION,
    )


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
    """Queue truth: portal PDF URL present and download not yet durable on CDN.

    ``fetched_local`` waits for the publish lane — not re-fetched from portal.
    Attempt-capped poison items become blocked.
    """
    if item.removed_from_source:
        return False
    item_src = (item.source or "").strip().lower()
    src = (source or item_src).strip().lower()
    if item_src != src:
        return False
    if src not in ACTIVE_SOURCES:
        return False
    if item.download == "done" or item.download == "fetched_local":
        return False
    if item.download == "blocked" or item.download_attempts >= MAX_STAGE_ATTEMPTS:
        return False
    portal = (item.portal_doc_url or "").strip()
    if not portal and src == "mstc":
        item.portal_doc_url = mstc_portal_doc_url()
        portal = item.portal_doc_url
    if not portal:
        return False
    closing = _item_closing_dt(item)
    if closing is None:
        return False
    from scraper.filters import resolve_min_closing

    if closing < resolve_min_closing():
        return False
    return True


def publish_eligible(item: LedgerItem, *, source: str | None = None) -> bool:
    """Local file staged; needs R2 publish to become download=done."""
    if item.removed_from_source:
        return False
    item_src = (item.source or "").strip().lower()
    src = (source or item_src).strip().lower()
    if src and item_src != src:
        return False
    if item.download != "fetched_local":
        return False
    path = (item.local_doc_path or "").strip()
    return bool(path)


def select_for_publish(
    ledger: PipelineLedger,
    *,
    limit: int,
    source: str | None = None,
) -> list[LedgerItem]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    eligible = [i for i in ledger.items if publish_eligible(i, source=source)]
    eligible.sort(key=lambda i: (-i.priority_score, i.first_seen_at or "", i.stable_key))
    return eligible[:limit]


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
            0 if i.download in ("pending", "failed", "blocked") else 1,
            -i.priority_score,
            i.first_seen_at or "",
            i.stable_key,
        )
    )
    return eligible[:limit]


def classify_download_queue_item(item: LedgerItem) -> str:
    if item.download != "done":
        return "new"
    return "done"


def select_for_parse(ledger: PipelineLedger, *, limit: int | None = None) -> list[LedgerItem]:
    eligible = [
        i
        for i in ledger.items
        if i.download == "done"
        and media_doc_url(i)
        and media_doc_path(i)
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


def count_parse_eligible(ledger: PipelineLedger) -> int:
    return len(select_for_parse(ledger, limit=None))


def count_download_pending(ledger: PipelineLedger, *, source: str | None = None) -> int:
    if source:
        return sum(1 for i in ledger.items if download_eligible(i, source=source))
    return sum(
        1
        for i in ledger.items
        if download_eligible(i, source="mstc") or download_eligible(i, source="gem_forward")
    )


def _item_closing_dt(item: LedgerItem) -> datetime | None:
    from scraper.qa_summary import _parse_closing

    return _parse_closing(item.closing)


def item_passes_min_closing(
    item: LedgerItem,
    *,
    min_closing_date: str | None = None,
    min_closing: datetime | None = None,
) -> bool:
    """True when closing is present and >= boundary (now+12h or forced date/ISO)."""
    from scraper.filters import parse_min_closing_boundary, resolve_min_closing

    if min_closing is not None:
        boundary = min_closing
    elif min_closing_date:
        boundary = parse_min_closing_boundary(min_closing_date)
    else:
        boundary = resolve_min_closing()
    closing = _item_closing_dt(item)
    if closing is None:
        return False
    return closing >= boundary


def select_publishable_future(
    ledger: PipelineLedger,
    *,
    min_closing_date: str | None = None,
) -> list[LedgerItem]:
    from scraper.filters import resolve_min_closing

    boundary = (
        resolve_min_closing(min_closing_date)
        if min_closing_date
        else resolve_min_closing()
    )
    return [
        i
        for i in select_publishable(ledger)
        if item_passes_min_closing(i, min_closing=boundary)
    ]


def count_publishable_future(
    ledger: PipelineLedger,
    *,
    min_closing_date: str | None = None,
) -> int:
    return len(select_publishable_future(ledger, min_closing_date=min_closing_date))


def pipeline_truth_snapshot(
    ledger: PipelineLedger,
    *,
    pdf_disk_n: int | None = None,
    parsed_disk_n: int | None = None,
    live_n: int | None = None,
    min_closing_date: str | None = None,
) -> dict[str, Any]:
    """Ledger-truth backlog vs optional Hostinger/live inventory counts."""
    from scraper.config import MIN_CLOSING_HOURS_AHEAD
    from scraper.filters import resolve_min_closing

    boundary_dt = (
        resolve_min_closing(min_closing_date)
        if min_closing_date
        else resolve_min_closing()
    )
    boundary = boundary_dt.isoformat()
    publishable_all = sum(1 for i in ledger.items if compute_publishable(i))
    publishable_future = count_publishable_future(ledger, min_closing_date=boundary)
    parse_done = sum(1 for i in ledger.items if i.parse == "done")
    parse_eligible = count_parse_eligible(ledger)
    download_pending = count_download_pending(ledger)
    aged_out_parsed = max(0, publishable_all - publishable_future)
    orphan_pdf_estimate = None
    if pdf_disk_n is not None:
        linked = sum(
            1
            for i in ledger.items
            if (i.hostinger_doc_path or "").strip().startswith("pdfs/")
            and i.download == "done"
        )
        orphan_pdf_estimate = max(0, int(pdf_disk_n) - linked)
    return {
        "schema_version": 1,
        "min_closing_date": boundary,
        "min_closing_at": boundary,
        "min_closing_hours_ahead": (
            None if min_closing_date else MIN_CLOSING_HOURS_AHEAD
        ),
        "pdfs_on_disk": pdf_disk_n,
        "parsed_on_disk": parsed_disk_n,
        "live_export_count": live_n,
        "download_pending": download_pending,
        "download_pending_mstc": count_download_pending(ledger, source="mstc"),
        "download_pending_gem": count_download_pending(ledger, source="gem_forward"),
        "parse_eligible": parse_eligible,
        "parse_done": parse_done,
        "publishable_all": publishable_all,
        "publishable_future": publishable_future,
        "aged_out_parsed": aged_out_parsed,
        "orphan_pdf_estimate": orphan_pdf_estimate,
        "naive_pdf_minus_parsed": (
            (int(pdf_disk_n) - int(parsed_disk_n))
            if pdf_disk_n is not None and parsed_disk_n is not None
            else None
        ),
        "note": "Backlog = parse_eligible / publishable_future; disk counts are inventory only",
    }


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
        # Missing CDN doc → must download / publish again
        if existing.download == "done" and not media_doc_url(existing):
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
    local_doc_path: str | None = None,
    object_doc_url: str | None = None,
    fetched_local_only: bool = False,
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
    # Prefer explicit CDN URL; else build from relative key via R2_PUBLIC_BASE_URL.
    if ok and hostinger_doc_path and not object_doc_url:
        object_doc_url = public_doc_url(hostinger_doc_path)
    if ok and hostinger_doc_path and not hostinger_doc_url:
        # Keep field populated for legacy readers; value is now CDN URL.
        hostinger_doc_url = object_doc_url or public_doc_url(hostinger_doc_path)

    if ok and fetched_local_only and local_doc_path:
        # Portal fetch succeeded; publish lane will flush to R2.
        item.download = "fetched_local"
        item.download_error = None
        item.local_doc_path = local_doc_path
        if hostinger_doc_path:
            item.hostinger_doc_path = hostinger_doc_path
        if doc_sha256:
            item.doc_sha256 = doc_sha256
        if raw_html_path:
            item.raw_html_path = raw_html_path
        if object_doc_url:
            item.object_doc_url = object_doc_url
    elif ok and hostinger_doc_path and (object_doc_url or hostinger_doc_url):
        prev_sha = (item.doc_sha256 or "").strip()
        new_sha = (doc_sha256 or "").strip()
        # Same bytes already on ledger → do not wipe parse/deploy (VPS re-touch / CDN hit).
        effective_changed = bool(content_changed)
        if new_sha and prev_sha and new_sha == prev_sha:
            effective_changed = False
        elif not new_sha and prev_sha and item.parse == "done":
            effective_changed = False
        item.download = "done"
        item.download_error = None
        item.hostinger_doc_path = hostinger_doc_path
        item.object_doc_url = object_doc_url or hostinger_doc_url
        item.hostinger_doc_url = item.object_doc_url
        item.local_doc_path = local_doc_path or item.local_doc_path
        if doc_sha256:
            item.doc_sha256 = doc_sha256
        if raw_html_path:
            item.raw_html_path = raw_html_path
        if effective_changed:
            item.parse = "pending"
            item.lots_count = 0
            item.deploy = "pending"
    else:
        # Any failure → pending (status is the only re-queue signal), unless capped.
        item.download_error = error or "download incomplete — CDN doc required"
        # Keep local staging on transport/flush failure so publish can retry.
        if not (local_doc_path or item.local_doc_path):
            item.hostinger_doc_path = None
            item.hostinger_doc_url = None
            item.object_doc_url = None
            item.doc_sha256 = None
            item.download = "pending"
        else:
            item.local_doc_path = local_doc_path or item.local_doc_path
            item.download = "fetched_local"
            item.download_error = error or "awaiting R2 publish"
        if item.download_attempts >= MAX_STAGE_ATTEMPTS and item.download != "fetched_local":
            item.download = "blocked"
    _replace_item(ledger, item)
    return item


def mark_download_fetched_local(
    ledger: PipelineLedger,
    stable_key: str,
    *,
    local_doc_path: str,
    hostinger_doc_path: str | None = None,
    doc_sha256: str | None = None,
    raw_html_path: str | None = None,
) -> LedgerItem | None:
    return mark_download(
        ledger,
        stable_key,
        ok=True,
        fetched_local_only=True,
        local_doc_path=local_doc_path,
        hostinger_doc_path=hostinger_doc_path,
        doc_sha256=doc_sha256,
        raw_html_path=raw_html_path,
    )


def mark_parse(
    ledger: PipelineLedger,
    stable_key: str,
    *,
    ok: bool,
    lots_count: int = 0,
    parsed_path: str | None = None,
    error: str | None = None,
    parser_version: str | None = None,
    # Durability/save/verify failures stay pending (re-queueable), like download.
    durability_failed: bool = False,
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
        # Always stamp version on success so GeM upgrade requeue cannot loop.
        from scraper.config import PARSER_CACHE_VERSION

        item.parser_version = str(parser_version or PARSER_CACHE_VERSION)
        item.deploy = "pending"
    elif durability_failed:
        # Hostinger save/verify (or missing doc) — status-only re-queue.
        item.lots_count = 0
        item.parsed_path = None
        item.parse_error = error or "parse durability incomplete — hostinger artifact required"
        item.parse = "pending"
    else:
        # Content failure (e.g. no lots).
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
    attempts: int = 4,
) -> bool:
    import time

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
    from scraper.hostinger_ssh import rsync_timeout_args, run_rsync_with_retries

    cmd = ["rsync", "-az", *rsync_timeout_args(), "-e", _ssh_cmd(cfg), remote, str(local)]
    last_exc: Exception | None = None
    tries = max(1, int(attempts))
    # Cap per-attempt wall clock so soft hangs fail fast (was up to 300s×4).
    per_try = min(int(timeout_sec), 90)
    for attempt in range(1, tries + 1):
        try:
            run_rsync_with_retries(
                cmd,
                timeout_sec=per_try,
                label="ledger-pull",
                attempts=1,
            )
            if attempt > 1:
                logger.info("ledger pull succeeded on attempt %s/%s", attempt, tries)
            return True
        except Exception as exc:
            last_exc = exc
            logger.info("ledger pull attempt %s/%s failed: %s", attempt, tries, exc)
            if attempt < tries:
                time.sleep(min(15, 3 * attempt))
    msg = f"ledger pull failed after {tries} attempts: {last_exc}"
    if require:
        logger.error(msg)
        raise RuntimeError(msg) from last_exc
    logger.info("ledger pull skipped/failed: %s", last_exc)
    return False


def push_ledger(*, local_path: Path | None = None, timeout_sec: int = 120) -> bool:
    """Push ledger to Hostinger after merging any concurrent remote updates.

    VPS download and GHA parse both mutate the same file. Blind rsync push was
    last-writer-wins and wiped parse=done marks (build then saw publishable=0).
    """
    import os
    import time

    local = Path(local_path or DEFAULT_LEDGER_PATH)
    if not local.is_file():
        return False
    cfg = _hostinger_ssh_config()
    if cfg is None or shutil.which("rsync") is None:
        return False
    remote_root = remote_pipeline_root(cfg["remote_dir"])
    target = f"{cfg['username']}@{cfg['host']}"
    from scraper.hostinger_ssh import run_ssh, rsync_timeout_args, run_rsync_with_retries

    try:
        run_ssh(cfg, f"mkdir -p {remote_root}", timeout_sec=60, multiplex=False)
    except Exception as exc:
        logger.warning("ledger remote mkdir failed: %s", exc)
        return False

    # Merge-before-push: pull current remote, union with local, then write+push.
    remote_tmp = local.parent / f".pipeline_ledger.remote.{os.getpid()}.{int(time.time())}.json"
    remote = f"{target}:{remote_root}/pipeline_ledger.json"
    try:
        pull_cmd = ["rsync", "-az", *rsync_timeout_args(), "-e", _ssh_cmd(cfg), remote, str(remote_tmp)]
        try:
            run_rsync_with_retries(
                pull_cmd,
                timeout_sec=min(int(timeout_sec), 60),
                label="ledger-push-premerge-pull",
                attempts=2,
            )
        except Exception as exc:
            logger.info("ledger push pre-merge pull skipped: %s", exc)
        if remote_tmp.is_file():
            try:
                ours = load_ledger(local)
                theirs = load_ledger(remote_tmp)
                merged = merge_ledgers(ours, theirs)
                write_ledger(merged, local)
                logger.info(
                    "ledger merge-before-push ours=%d theirs=%d merged=%d publishable=%d",
                    len(ours.items),
                    len(theirs.items),
                    len(merged.items),
                    sum(1 for i in merged.items if compute_publishable(i)),
                )
            except Exception as exc:
                logger.warning("ledger merge-before-push failed (pushing local as-is): %s", exc)
    finally:
        try:
            remote_tmp.unlink(missing_ok=True)
        except OSError:
            pass

    cmd = ["rsync", "-az", *rsync_timeout_args(), "-e", _ssh_cmd(cfg), str(local), remote]
    try:
        run_rsync_with_retries(
            cmd,
            timeout_sec=min(int(timeout_sec), 90),
            label="ledger-push",
            attempts=3,
        )
        return True
    except Exception as exc:
        logger.warning("ledger push failed: %s", exc)
        return False
