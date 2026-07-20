"""Portal fetch → local durable files (no Hostinger push)."""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from scraper.download_throttle import DownloadThrottle
from scraper.main import enrich_auction, resolve_auction_listing
from scraper.pdf_downloader import validate_pdf_file
from scraper.pdf_flush import _sha256_file
from scraper.raw_store import has_raw_html, raw_html_rel_path, save_raw_html

logger = logging.getLogger("scraper.download_engine")


def _host_from_url(url: str, fallback: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host or fallback
    except Exception:
        return fallback


def fetch_mstc_to_local(
    *,
    item: Any,
    pdf_dir: Path,
    public_dir: Path,
    raw_dir: Path,
    skip_pdf: bool,
    stats: dict[str, Any],
    throttle: DownloadThrottle,
) -> dict[str, Any]:
    """Fetch MSTC HTML+PDF to local public pdfs/. Does not push Hostinger."""
    aid = str(item.source_auction_id)
    host = "www.mstcecommerce.com"
    throttle.for_host(host).wait_turn()
    t0 = time.monotonic()
    try:
        if skip_pdf:
            return {
                "stable_key": item.stable_key,
                "source": "mstc",
                "source_auction_id": aid,
                "ok": False,
                "error": "skip_pdf set — Hostinger durability required",
            }
        base, _ = resolve_auction_listing(aid)
        base.source = "mstc"
        downloaded = enrich_auction(
            base,
            pdf_dir=pdf_dir,
            skip_pdf=False,
            stats=stats,
            mode="download_only",
            raw_dir=raw_dir,
        )
        has_html = has_raw_html("mstc", aid, raw_dir=raw_dir)
        local_pdf = pdf_dir / f"{aid}.pdf"
        has_pdf = validate_pdf_file(local_pdf)
        if not (has_html and has_pdf):
            parts = list(downloaded.errors or [])
            if not has_html:
                parts.append("missing raw HTML")
            if not has_pdf:
                parts.append("missing or invalid catalogue PDF")
            raise RuntimeError("; ".join(parts) if parts else "download incomplete")

        public_pdf = public_dir / "pdfs" / f"{aid}.pdf"
        public_pdf.parent.mkdir(parents=True, exist_ok=True)
        if local_pdf.resolve() != public_pdf.resolve():
            shutil.copy2(local_pdf, public_pdf)

        # Sniff: reject HTML saved as PDF
        head = public_pdf.read_bytes()[:16]
        if not head.startswith(b"%PDF"):
            raise RuntimeError("local file is not a PDF (magic)")

        sha = _sha256_file(public_pdf)
        throttle.for_host(host).record(ok=True, latency_sec=time.monotonic() - t0)
        return {
            "stable_key": item.stable_key,
            "source": "mstc",
            "source_auction_id": aid,
            "ok": True,
            "local_path": str(public_pdf),
            "hostinger_doc_path": f"pdfs/{aid}.pdf",
            "doc_sha256": sha,
            "raw_html_path": raw_html_rel_path("mstc", aid),
            "bytes": public_pdf.stat().st_size,
            "error": None,
        }
    except Exception as exc:
        throttle.for_host(host).record(ok=False, latency_sec=time.monotonic() - t0)
        logger.warning("MSTC fetch failed %s: %s", item.stable_key, exc)
        return {
            "stable_key": item.stable_key,
            "source": "mstc",
            "source_auction_id": aid,
            "ok": False,
            "error": str(exc),
            "raw_html_path": raw_html_rel_path("mstc", aid)
            if has_raw_html("mstc", aid, raw_dir=raw_dir)
            else None,
        }


def fetch_gem_to_local(
    *,
    item: Any,
    raw_dir: Path,
    public_dir: Path,
    client: Any | None,
    throttle: DownloadThrottle,
) -> dict[str, Any]:
    """Fetch GeM portal doc to local docs/gem/. Does not push Hostinger."""
    from scraper.gem_forward_client import GemForwardClient
    from scraper.gem_scrap_samples_fetch import _download_binary

    aid = str(item.source_auction_id or "").strip()
    portal = (getattr(item, "portal_doc_url", None) or "").strip()
    host = _host_from_url(portal, "gem.gov.in")
    throttle.for_host(host).wait_turn()
    t0 = time.monotonic()
    if not portal:
        return {
            "stable_key": item.stable_key,
            "source": "gem_forward",
            "source_auction_id": aid,
            "ok": False,
            "error": "missing portal_doc_url",
        }
    try:
        gem = client or GemForwardClient()
        if client is None:
            gem.init_session()
        detail = getattr(item, "detail_url", None) or ""
        if "/eprocure/" in str(detail):
            notice_path = "/eprocure/" + str(detail).split("/eprocure/", 1)[-1]
            try:
                html = gem.get_html(notice_path)
                save_raw_html("gem_forward", aid, html, raw_dir=raw_dir)
            except Exception:
                pass
        body = _download_binary(gem, portal)
        if len(body) < 500:
            raise RuntimeError(f"gem doc too small ({len(body)} bytes)")
        # Reject HTML error pages
        head = body[:200].lstrip().lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html"):
            raise RuntimeError("gem response looks like HTML, not a document")

        ext = "pdf" if body[:4] == b"%PDF" else "bin"
        rel = f"docs/gem/{aid}.{ext}"
        out_path = public_dir / "docs" / "gem" / f"{aid}.{ext}"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part = out_path.with_suffix(out_path.suffix + ".part")
        part.write_bytes(body)
        part.replace(out_path)

        throttle.for_host(host).record(ok=True, latency_sec=time.monotonic() - t0)
        return {
            "stable_key": item.stable_key,
            "source": "gem_forward",
            "source_auction_id": aid,
            "ok": True,
            "local_path": str(out_path),
            "hostinger_doc_path": rel,
            "doc_sha256": hashlib.sha256(body).hexdigest(),
            "raw_html_path": raw_html_rel_path("gem_forward", aid)
            if has_raw_html("gem_forward", aid, raw_dir=raw_dir)
            else None,
            "bytes": len(body),
            "error": None,
        }
    except Exception as exc:
        throttle.for_host(host).record(ok=False, latency_sec=time.monotonic() - t0)
        logger.warning("GeM fetch failed %s: %s", item.stable_key, exc)
        return {
            "stable_key": item.stable_key,
            "source": "gem_forward",
            "source_auction_id": aid,
            "ok": False,
            "error": str(exc),
        }


def worker_count_for_source(source: str) -> int:
    from scraper.config import (
        DOWNLOAD_FETCH_WORKERS,
        DOWNLOAD_FETCH_WORKERS_GEM,
        DOWNLOAD_FETCH_WORKERS_MSTC,
    )

    n = int(DOWNLOAD_FETCH_WORKERS or 0)
    if n > 0:
        return max(1, n)
    if (source or "").strip().lower() == "gem_forward":
        return max(1, int(DOWNLOAD_FETCH_WORKERS_GEM))
    return max(1, int(DOWNLOAD_FETCH_WORKERS_MSTC))
