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


def _gem_notice_path(item: Any) -> str | None:
    detail = str(getattr(item, "detail_url", None) or "").strip()
    if "/eprocure/" in detail:
        return "/eprocure/" + detail.split("/eprocure/", 1)[-1]
    for url in getattr(item, "document_urls", None) or []:
        u = str(url or "")
        if "view-auction-notice" in u and "/eprocure/" in u:
            return "/eprocure/" + u.split("/eprocure/", 1)[-1]
    return None


def _gem_pick_catalogue(
    *,
    gem: Any,
    aid: str,
    notice_html: str,
    delay_sec: float,
) -> tuple[bytes, str]:
    """Notice/shell HTML → file-list → validated binary. Never saves HTML shells."""
    import re
    import time as _time

    from scraper.gem_doc_validate import extension_for_kind, is_gem_document_bytes
    from scraper.gem_scrap_samples_fetch import (
        _download_binary,
        find_file_list_url,
        parse_file_list_html,
    )

    file_list_path = find_file_list_url(notice_html or "", aid)
    if not file_list_path:
        raise RuntimeError("gem_no_file_list")

    _time.sleep(max(0.0, float(delay_sec)))
    file_list_html = gem.get_html(file_list_path)
    docs_meta = parse_file_list_html(file_list_html)
    candidates: list[tuple[bytes, str, int]] = []
    last_err = "gem_no_attachments"
    for doc in docs_meta:
        dl_path = (doc.get("download_path") or "").strip()
        if not dl_path or "file-download" not in dl_path:
            continue
        _time.sleep(max(0.0, float(delay_sec)))
        try:
            content = _download_binary(gem, dl_path)
        except Exception as exc:
            last_err = f"gem_file_download_failed: {exc}"
            continue
        ok, kind, err = is_gem_document_bytes(content)
        if not ok:
            last_err = err or "gem_html_rejected"
            continue
        candidates.append((content, extension_for_kind(kind), len(content)))

    if not candidates:
        # Fallback: notice PDF endpoint embedded in notice HTML
        pdf_re = re.compile(
            rf"/eprocure/xcommon/view-auction-notice/pdf/{re.escape(aid)}/[^\"'\s<>]+",
            re.I,
        )
        m = pdf_re.search(notice_html or "")
        if m:
            _time.sleep(max(0.0, float(delay_sec)))
            content = _download_binary(gem, m.group(0))
            ok, kind, err = is_gem_document_bytes(content)
            if ok:
                return content, extension_for_kind(kind)
            last_err = err or last_err
        raise RuntimeError(last_err)

    pdfs = [c for c in candidates if c[1] == "pdf"]
    pick = max(pdfs or candidates, key=lambda c: c[2])
    return pick[0], pick[1]


def fetch_gem_to_local(
    *,
    item: Any,
    raw_dir: Path,
    public_dir: Path,
    client: Any | None,
    throttle: DownloadThrottle,
) -> dict[str, Any]:
    """Fetch GeM catalogue via notice → file-list → file-download (never shell URL)."""
    from scraper.config import GEM_FORWARD_REQUEST_DELAY_SEC
    from scraper.gem_doc_validate import is_gem_document_bytes
    from scraper.gem_forward_client import GemForwardClient

    aid = str(item.source_auction_id or "").strip()
    portal = (getattr(item, "portal_doc_url", None) or "").strip()
    host = _host_from_url(portal or "https://forwardauction.gem.gov.in", "forwardauction.gem.gov.in")
    throttle.for_host(host).wait_turn()
    t0 = time.monotonic()
    # portal_doc_url is audit/hint only — download still proceeds via notice/file-list.
    if not aid:
        return {
            "stable_key": item.stable_key,
            "source": "gem_forward",
            "source_auction_id": aid,
            "ok": False,
            "error": "missing source_auction_id",
        }
    try:
        gem = client or GemForwardClient()
        if client is None:
            gem.init_session()

        notice_html = ""
        notice_path = _gem_notice_path(item)
        if notice_path:
            try:
                notice_html = gem.get_html(notice_path)
                save_raw_html("gem_forward", aid, notice_html, raw_dir=raw_dir)
            except Exception as exc:
                logger.warning("GeM %s notice fetch failed: %s", aid, exc)

        # Listing shell URL is discovery HTML only — never saved as the document.
        if not notice_html and portal and "eauction-download-document" in portal:
            try:
                notice_html = gem.get_html(portal)
            except Exception as exc:
                logger.warning("GeM %s shell fetch failed: %s", aid, exc)

        if not notice_html:
            raise RuntimeError("gem_no_notice_html")

        body, ext = _gem_pick_catalogue(
            gem=gem,
            aid=aid,
            notice_html=notice_html,
            delay_sec=float(GEM_FORWARD_REQUEST_DELAY_SEC),
        )
        ok, _kind, err = is_gem_document_bytes(body)
        if not ok:
            raise RuntimeError(err or "gem_html_rejected")

        # Never write poison .bin for HTML; only known extensions.
        if ext not in {"pdf", "docx", "doc", "zip"}:
            raise RuntimeError("gem_unknown_magic")

        rel = f"docs/gem/{aid}.{ext}"
        out_path = public_dir / "docs" / "gem" / f"{aid}.{ext}"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove prior poison .bin / wrong-ext siblings for this auction.
        for stale in out_path.parent.glob(f"{aid}.*"):
            if stale.resolve() != out_path.resolve():
                try:
                    stale.unlink()
                except OSError:
                    pass
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
