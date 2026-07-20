"""Fast PDF text extraction (PyMuPDF primary) + lot parsing helpers."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("scraper.parse_engine")


def extract_pdf_text_pymupdf(pdf_path: Path) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    try:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text") or "")
        return "\n".join(parts)
    finally:
        doc.close()


def parse_mstc_pdf_fast(pdf_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Return (lots, header, engine_used). PyMuPDF text first; pdfplumber fallback."""
    from scraper.pdf_parser import (
        extract_lots_from_pdfplumber,
        extract_pdf_text,
        parse_lot_block,
        parse_pdf_header,
        split_lot_blocks,
        _parse_pdf_emd_header,
        _field,
    )

    path = Path(pdf_path)
    t0 = time.perf_counter()

    # 1) PyMuPDF text → lot blocks (fast path)
    try:
        text = extract_pdf_text_pymupdf(path)
        blocks = split_lot_blocks(text)
        lots = [parse_lot_block(b) for b in blocks]
        if lots:
            header_src = text[:5000]
            emd = _parse_pdf_emd_header(header_src)
            header = {
                "auction_number": _field(header_src, "Auction No")
                or _field(header_src, "Auction Number"),
                "seller": _field(header_src, "Seller Name") or _field(header_src, "Seller"),
                "location": _field(header_src, "Location"),
                "opening": _field(header_src, "Opening Date"),
                "closing": _field(header_src, "Closing Date"),
                **emd,
            }
            logger.info(
                "pymupdf lots=%d file=%s ms=%.0f",
                len(lots),
                path.name,
                (time.perf_counter() - t0) * 1000,
            )
            return lots, header, "pymupdf"
    except Exception as exc:
        logger.warning("pymupdf extract failed %s: %s", path.name, exc)

    # 2) pdfplumber tables
    try:
        lots = extract_lots_from_pdfplumber(path)
        if lots:
            header = parse_pdf_header(path)
            logger.info(
                "pdfplumber lots=%d file=%s ms=%.0f",
                len(lots),
                path.name,
                (time.perf_counter() - t0) * 1000,
            )
            return lots, header, "pdfplumber"
    except Exception as exc:
        logger.warning("pdfplumber failed %s: %s", path.name, exc)

    # 3) pypdf text fallback
    text = extract_pdf_text(path)
    blocks = split_lot_blocks(text)
    lots = [parse_lot_block(b) for b in blocks]
    header = parse_pdf_header(path)
    logger.info(
        "pypdf lots=%d file=%s ms=%.0f",
        len(lots),
        path.name,
        (time.perf_counter() - t0) * 1000,
    )
    return lots, header, "pypdf"


def worker_parse_mstc(spec: dict[str, Any]) -> dict[str, Any]:
    """Picklable process-pool worker for one MSTC auction."""
    t0 = time.perf_counter()
    aid = str(spec.get("source_auction_id") or "")
    stable_key = str(spec.get("stable_key") or f"mstc:{aid}")
    pdf_path = Path(spec["pdf_path"])
    try:
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF missing: {pdf_path}")
        lots, header, engine = parse_mstc_pdf_fast(pdf_path)
        # Optional HTML enrich fields from disk (best-effort, in worker).
        html_data = None
        raw_html_path = spec.get("raw_html_path")
        if raw_html_path and Path(raw_html_path).is_file():
            try:
                from scraper.html_parser import parse_html_detail

                html_data = parse_html_detail(Path(raw_html_path).read_text(encoding="utf-8", errors="replace"))
            except Exception:
                html_data = None

        from scraper.models import AuctionRecord, ExtractionStatus
        from scraper.merger import merge_auction_record
        from scraper.config import PDF_DETAIL_URL

        opening = spec.get("opening")
        closing = spec.get("closing")
        # Ledger may store ISO strings; AuctionRecord wants datetime | None.
        from datetime import datetime

        def _as_dt(v):
            if v is None or isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except Exception:
                return None

        base = AuctionRecord(
            id=aid,
            auction_number=str(spec.get("auction_number") or aid),
            region=str(spec.get("region") or ""),
            office=str(spec.get("office") or ""),
            state=spec.get("state"),
            seller=spec.get("seller"),
            source="mstc",
            source_auction_id=aid,
            mstc_html_url=spec.get("detail_url")
            or f"https://www.mstcindia.co.in/TenderEntry/Lot_Item_Details_AucID.aspx?ARID={aid}",
            detail_url=spec.get("detail_url"),
            source_pdf_url=PDF_DETAIL_URL,
            status=ExtractionStatus.LISTING_ONLY,
            opening=_as_dt(opening),
            closing=_as_dt(closing),
        )
        record = merge_auction_record(
            base,
            html_data=html_data,
            pdf_lots=lots,
            pdf_header=header,
            pdf_relative_url=spec.get("hostinger_doc_path") or f"pdfs/{aid}.pdf",
            source_pdf_url=PDF_DETAIL_URL,
        )
        rec = record.model_dump(mode="json")
        rec["pdf_url"] = spec.get("hostinger_doc_path") or f"pdfs/{aid}.pdf"
        rec["hostinger_doc_url"] = spec.get("hostinger_doc_url")
        rec["hostinger_doc_path"] = spec.get("hostinger_doc_path")
        rec["source_pdf_url"] = spec.get("portal_doc_url") or PDF_DETAIL_URL
        n_lots = len(rec.get("lots") or [])
        return {
            "stable_key": stable_key,
            "source": "mstc",
            "source_auction_id": aid,
            "ok": n_lots > 0,
            "lots_count": n_lots,
            "record": rec,
            "engine": engine,
            "error": None if n_lots > 0 else "no lots",
            "parse_ms": int((time.perf_counter() - t0) * 1000),
            "doc_sha256": spec.get("doc_sha256"),
        }
    except Exception as exc:
        return {
            "stable_key": stable_key,
            "source": "mstc",
            "source_auction_id": aid,
            "ok": False,
            "lots_count": 0,
            "record": None,
            "engine": None,
            "error": str(exc),
            "parse_ms": int((time.perf_counter() - t0) * 1000),
            "doc_sha256": spec.get("doc_sha256"),
        }
