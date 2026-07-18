"""Mid-run catalogue PDF flush queue → Hostinger ``pdfs/``.

Keeps the download auction cap independent of flush cadence. A download is only
considered durable on Hostinger when ``LedgerItem.media_synced is True``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from scraper.media_sync import media_push_required
from scraper.pipeline_ledger import PipelineLedger, _replace_item
from scraper.raw_store import RawSyncResult, push_public_pdf_files

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pdf_flush")


def _now_iso() -> str:
    return datetime.now(IST).isoformat()


def auction_id_from_pdf_name(name: str) -> str:
    return Path(name).stem


def mark_pdfs_hostinger_synced(
    ledger: PipelineLedger,
    filenames: list[str],
    *,
    synced: bool,
) -> int:
    """Set ``media_synced`` for MSTC rows matching PDF basenames. Returns count updated."""
    now = _now_iso()
    updated = 0
    by_key = ledger.by_key()
    for name in filenames:
        aid = auction_id_from_pdf_name(name)
        if not aid:
            continue
        item = by_key.get(f"mstc:{aid}")
        if item is None:
            continue
        item.media_synced = synced
        item.media_synced_at = now if synced else None
        if not synced and item.download == "done":
            # Keep download=done (local assets OK) but force re-selection via media_synced=False.
            item.last_error = item.last_error or "awaiting Hostinger PDF sync"
        _replace_item(ledger, item)
        updated += 1
    return updated


@dataclass
class CataloguePdfFlushQueue:
    """Buffer validated local PDFs and flush them to Hostinger every N files."""

    public_dir: Path
    ledger: PipelineLedger
    flush_every: int = 25
    skip: bool = False
    phase: Callable[[str], None] = field(default=lambda _msg: None)
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    _pending: list[str] = field(default_factory=list, init=False)
    _pending_set: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        self.flush_every = max(1, int(self.flush_every))
        self.stats.setdefault("pdf_hostinger_flushed", 0)
        self.stats.setdefault("pdf_hostinger_flush_batches", 0)
        self.stats.setdefault("pdf_hostinger_flush_failures", 0)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def enqueue(self, auction_id: str) -> None:
        name = f"{str(auction_id).strip()}.pdf"
        if not str(auction_id).strip() or name in self._pending_set:
            return
        self._pending.append(name)
        self._pending_set.add(name)
        # Local durable, Hostinger not yet confirmed.
        mark_pdfs_hostinger_synced(self.ledger, [name], synced=False)

    def maybe_flush(self) -> RawSyncResult | None:
        if self.skip or self.pending_count < self.flush_every:
            return None
        return self.flush(force=True)

    def flush(self, *, force: bool = True) -> RawSyncResult | None:
        if self.skip or not self._pending:
            return None
        if not force and self.pending_count < self.flush_every:
            return None

        batch = list(self._pending)
        self._pending.clear()
        self._pending_set.clear()

        self.phase(f"media: mid-run PDF flush ({len(batch)} file(s)) -> Hostinger")
        result = push_public_pdf_files(public_dir=self.public_dir, filenames=batch)
        self.stats["pdf_hostinger_flush_batches"] = int(self.stats["pdf_hostinger_flush_batches"]) + 1

        pushed = list(result.files) if result.ok else []
        if result.ok and pushed:
            mark_pdfs_hostinger_synced(self.ledger, pushed, synced=True)
            self.stats["pdf_hostinger_flushed"] = int(self.stats["pdf_hostinger_flushed"]) + len(pushed)
            msg = (
                f"mid-run PDF flush ok (+{len(pushed)}; "
                f"total={self.stats['pdf_hostinger_flushed']})"
            )
            self.warnings.append(msg)
            self.phase(
                f"Hostinger PDF flush ok +{len(pushed)} "
                f"(flushed_total={self.stats['pdf_hostinger_flushed']})"
            )
            # Any requested but not pushed stay unsynced and re-queued.
            leftover = [n for n in batch if n not in set(pushed)]
            for name in leftover:
                self._pending.append(name)
                self._pending_set.add(name)
            return result

        self.stats["pdf_hostinger_flush_failures"] = int(self.stats["pdf_hostinger_flush_failures"]) + 1
        self.warnings.append(f"mid-run PDF flush failed: {result.message}")
        # Re-queue so a later force flush / emergency flush can retry.
        for name in batch:
            if name not in self._pending_set:
                self._pending.append(name)
                self._pending_set.add(name)
        mark_pdfs_hostinger_synced(self.ledger, batch, synced=False)

        if media_push_required():
            raise RuntimeError(f"mid-run PDF push to Hostinger failed: {result.message}")
        return result

    def emergency_flush(self) -> None:
        """Best-effort flush on job failure — never raises."""
        if self.skip or not self._pending:
            return
        try:
            self.phase(f"media: emergency PDF flush ({self.pending_count} file(s))")
            self.flush(force=True)
        except Exception as exc:
            logger.warning("emergency PDF flush failed: %s", exc)
            self.warnings.append(f"emergency PDF flush failed: {exc}")
