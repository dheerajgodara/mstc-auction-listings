"""Mid-run catalogue PDF flush queue → Hostinger ``pdfs/`` (ledger v3)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from scraper.media_sync import media_push_required
from scraper.object_store import upload_hostinger_rel
from scraper.pipeline_ledger import PipelineLedger, _replace_item, mark_download, public_doc_url
from scraper.raw_store import RawSyncResult, push_public_pdf_files

logger = logging.getLogger("scraper.pdf_flush")


def auction_id_from_pdf_name(name: str) -> str:
    return Path(name).stem


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hostinger_doc_url(
    url: str,
    *,
    timeout_sec: float = 30.0,
    sniff_magic: bool = False,
) -> bool:
    """Return True when the public CDN/media URL responds with HTTP 200.

    Name retained for call-site compatibility; verification targets R2 CDN URLs.
    """
    from scraper.object_store import verify_public_object_url

    return verify_public_object_url(
        url, timeout_sec=timeout_sec, sniff_magic=sniff_magic
    )


def mark_pdfs_hostinger_synced(
    ledger: PipelineLedger,
    filenames: list[str],
    *,
    synced: bool,
    public_dir: Path | None = None,
) -> int:
    """Confirm CDN durability for MSTC PDFs (sets hostinger_doc_* + object_doc_url)."""
    updated = 0
    pdf_dir = (public_dir / "pdfs") if public_dir else None
    for name in filenames:
        aid = auction_id_from_pdf_name(name)
        if not aid:
            continue
        key = f"mstc:{aid}"
        item = ledger.by_key().get(key)
        if item is None:
            continue
        rel = f"pdfs/{aid}.pdf"
        if synced:
            sha = _sha256_file(pdf_dir / f"{aid}.pdf") if pdf_dir else None
            cdn = public_doc_url(rel)
            mark_download(
                ledger,
                key,
                ok=True,
                hostinger_doc_path=rel,
                hostinger_doc_url=cdn,
                object_doc_url=cdn,
                doc_sha256=sha,
                raw_html_path=item.raw_html_path,
                content_changed=True,
            )
        else:
            # Keep attempts stable: direct field patch, not another mark_download fail
            item.hostinger_doc_path = None
            item.hostinger_doc_url = None
            item.object_doc_url = None
            if item.download == "done":
                item.download = "pending"
            item.download_error = "awaiting R2 PDF sync"
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

        self.phase(f"media: mid-run PDF flush ({len(batch)} file(s)) -> R2 CDN")
        # Prefer R2 upload of local PDFs; Hostinger push only if R2 unavailable.
        from scraper.object_store import media_r2_only, r2_configured

        pushed: list[str] = []
        result: RawSyncResult
        if r2_configured() or media_r2_only():
            ok_names: list[str] = []
            err_parts: list[str] = []
            for name in batch:
                local = self.public_dir / "pdfs" / name
                up = upload_hostinger_rel(local, f"pdfs/{name}")
                if up.get("ok"):
                    ok_names.append(name)
                else:
                    err_parts.append(f"{name}:{up.get('error')}")
            result = RawSyncResult(
                attempted=True,
                ok=bool(ok_names) and not err_parts,
                message=(
                    f"r2 uploaded {len(ok_names)}/{len(batch)}"
                    + (f" errors={';'.join(err_parts[:3])}" if err_parts else "")
                ),
                files=ok_names,
            )
            pushed = ok_names
        else:
            result = push_public_pdf_files(public_dir=self.public_dir, filenames=batch)
            pushed = list(result.files) if result.ok else []
        self.stats["pdf_hostinger_flush_batches"] = int(self.stats["pdf_hostinger_flush_batches"]) + 1

        if result.ok and pushed:
            mark_pdfs_hostinger_synced(
                self.ledger, pushed, synced=True, public_dir=self.public_dir
            )
            self.stats["pdf_hostinger_flushed"] = int(self.stats["pdf_hostinger_flushed"]) + len(
                pushed
            )
            self.phase(
                f"R2 PDF flush ok +{len(pushed)} "
                f"(flushed_total={self.stats['pdf_hostinger_flushed']})"
            )
            leftover = [n for n in batch if n not in set(pushed)]
            for name in leftover:
                self._pending.append(name)
                self._pending_set.add(name)
            return result

        self.stats["pdf_hostinger_flush_failures"] = (
            int(self.stats["pdf_hostinger_flush_failures"]) + 1
        )
        self.warnings.append(f"mid-run PDF flush failed: {result.message}")
        for name in batch:
            if name not in self._pending_set:
                self._pending.append(name)
                self._pending_set.add(name)
        mark_pdfs_hostinger_synced(
            self.ledger, batch, synced=False, public_dir=self.public_dir
        )

        if media_push_required():
            raise RuntimeError(f"mid-run PDF push to R2 failed: {result.message}")
        return result

    def emergency_flush(self) -> None:
        if self.skip or not self._pending:
            return
        try:
            self.phase(f"media: emergency PDF flush ({self.pending_count} file(s))")
            self.flush(force=True)
        except Exception as exc:
            logger.warning("emergency PDF flush failed: %s", exc)
            self.warnings.append(f"emergency PDF flush failed: {exc}")
