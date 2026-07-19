"""Fetch closed GeM Forward pure-scrap auction results with full enrichment."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from scraper.category_map import normalize_gem_category
from scraper.config import (
    GEM_FORWARD_REQUEST_DELAY_SEC,
    GEM_FORWARD_STATUS_CLOSED,
    REPO_ROOT,
)
from scraper.emd import format_inr_amount, format_inr_or_dash, parse_emd_amount
from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError
from scraper.gem_forward_parser import (
    merge_auction,
    parse_detail_page,
    parse_listing_page,
    parse_rules_page,
)

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

_RESULT_PATH_RE = re.compile(
    r'/eprocure/xcommon/auction-result/(\d+)/\d+/([A-F0-9]+)', re.I
)
_FILE_LIST_RE = re.compile(r'file-list/(\d+)/([^"\']+)', re.I)
_FILE_DOWNLOAD_RE = re.compile(r'file-download/([^"\']+)', re.I)

_EXCLUDE_TITLE = re.compile(
    r"\b("
    r"vehicle|elv|end of life|car|bus|truck|motor|automobile|rvsf|"
    r"aircraft|helicopter|demolition|building|flat|plot|land|lease|"
    r"wheat|paddy|gram|channa|screening|e-?waste|ewaste|"
    r"machinery|compressor|generator|transformer|crane|excavator|"
    r"timber|wood|coal|mineral|ore"
    r")\b",
    re.I,
)
_INCLUDE_TITLE = re.compile(
    r"\b("
    r"scrap|iron|steel|metal|copper|alumin|brass|gi\s*sheet|"
    r"unserviceable|unsv|condemned|stores|empty\s*container|"
    r"non-?ferrous|ferrous|metallic|disposal\s+of"
    r")\b",
    re.I,
)

GEM_SCRAP_CATEGORY_ID = "8"  # General Scrap parent category
GEM_CLOSED_STATUS = GEM_FORWARD_STATUS_CLOSED


def is_pure_scrap_title(title: str, category: Optional[str] = None) -> bool:
    text = f"{title} {category or ''}"
    if _EXCLUDE_TITLE.search(text):
        return False
    if _INCLUDE_TITLE.search(text):
        return True
    cat = normalize_gem_category(category=category, title=title)
    return cat == "scrap"


def parse_listing_block(block: BeautifulSoup) -> dict[str, Any]:
    content = block.select_one("div.listing-content") or block
    index_label = content.select_one("div.index label")
    auction_id = None
    if index_label:
        match = re.search(r"Auction ID\s*:\s*(\d+)", index_label.get_text(" ", strip=True))
        auction_id = match.group(1) if match else None

    title_link = content.select_one("div.brief a")
    title = title_link.get_text(" ", strip=True) if title_link else ""
    notice_path = title_link["href"] if title_link and title_link.get("href") else ""

    result_link = block.select_one('a[href*="auction-result"]')
    result_path = result_link["href"] if result_link and result_link.get("href") else ""

    orgs = [
        d.get_text(" ", strip=True).lstrip("\uf0f7 ").strip()
        for d in content.select("span.x-dept-name")
        if d.get_text(strip=True)
    ]

    loc_parts = []
    loc_wrapper = content.select_one("div.date-icon.wid-27")
    if loc_wrapper and loc_wrapper.parent:
        loc_parts = [
            s.get_text(strip=True)
            for s in loc_wrapper.parent.select("span")
            if s.get_text(strip=True) not in {"-", "...", "View More"}
        ]
    city = loc_parts[0] if loc_parts else None
    district = loc_parts[1] if len(loc_parts) > 1 else None
    state = loc_parts[2] if len(loc_parts) > 2 else None
    pincode = loc_parts[-1] if loc_parts and loc_parts[-1].isdigit() and len(loc_parts[-1]) == 6 else None

    date_text = content.select_one("div.listing-date-info span.blink")
    opening = closing = None
    if date_text:
        pair = re.search(
            r"Start Date\s*:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}).*?"
            r"End Date\s*:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})",
            date_text.get_text(" ", strip=True),
            re.S,
        )
        if pair:
            from scraper.gem_forward_parser import parse_gem_datetime

            opening = parse_gem_datetime(pair.group(1))
            closing = parse_gem_datetime(pair.group(2))

    return {
        "auction_id": auction_id,
        "title": title,
        "notice_path": notice_path,
        "result_path": result_path,
        "organisation": orgs,
        "city": city,
        "district": district,
        "state": state,
        "pincode": pincode,
        "opening": opening.isoformat() if opening else None,
        "closing": closing.isoformat() if closing else None,
    }


def parse_result_page(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for table in soup.select("table"):
        headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
        if not headers:
            continue
        lower = [h.lower() for h in headers]
        if not any("winning" in h or "bid price" in h or "bidder" in h for h in lower):
            continue
        col_map = {h.lower(): i for i, h in enumerate(lower)}
        for tr in table.select("tbody tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not cells or not any(c.strip() for c in cells):
                continue
            if len(cells) >= 6:
                items.append(
                    {
                        "sr_no": cells[0],
                        "item_name": cells[1],
                        "winning_bidder": cells[2] if len(cells) > 2 else None,
                        "winning_bid_inr": parse_emd_amount(cells[3]) if len(cells) > 3 else None,
                        "winning_bid_text": cells[3] if len(cells) > 3 else None,
                        "bid_datetime": cells[4] if len(cells) > 4 else None,
                        "acceptance_status": cells[5] if len(cells) > 5 else None,
                        "remarks": cells[6] if len(cells) > 6 else None,
                    }
                )
    return items


def find_file_list_url(notice_html: str, auction_id: str) -> Optional[str]:
    # New GeM format: /ajax/file-list/0/44/0/{auction_id}/0/917/...
    new_pat = re.compile(
        rf"/eprocure/xcommon/ajax/file-list/[^\"']*?/{re.escape(auction_id)}/[^\"']+",
        re.I,
    )
    m = new_pat.search(notice_html)
    if m:
        return m.group(0)
    for match in _FILE_LIST_RE.finditer(notice_html):
        if match.group(1) == auction_id:
            return f"/eprocure/xcommon/ajax/file-list/{match.group(1)}/{match.group(2)}"
    soup = BeautifulSoup(notice_html, "lxml")
    for script in soup.select("script"):
        text = script.string or ""
        m = new_pat.search(text)
        if m:
            return m.group(0)
        match = _FILE_LIST_RE.search(text)
        if match and match.group(1) == auction_id:
            return f"/eprocure/xcommon/ajax/file-list/{match.group(1)}/{match.group(2)}"
    return None


def repo_relative_path(path: Path) -> str:
    """Return path relative to REPO_ROOT; works when path is relative or absolute."""
    return str(path.resolve().relative_to(REPO_ROOT.resolve()))


def _tender_doc_save_name(doc: dict[str, str], content: bytes) -> str:
    raw = (doc.get("filename") or "").strip()
    desc = (doc.get("description") or "Tender_document").strip()
    if content[:4] == b"%PDF":
        ext = ".pdf"
    elif content[:2] == b"PK":
        ext = ".docx"
    else:
        ext = Path(raw).suffix or ".bin"

    if raw.lower() in ("download", "") or not Path(raw).suffix:
        base = re.sub(r"[^\w.\-]+", "_", desc).strip("_") or "Tender_document"
        if not base.lower().endswith(ext):
            base = f"{Path(base).stem}{ext}"
        return base
    safe = re.sub(r"[^\w.\-]+", "_", raw).strip("_")
    if ext == ".pdf" and not safe.lower().endswith(".pdf") and content[:4] == b"%PDF":
        safe += ".pdf"
    elif ext == ".docx" and not safe.lower().endswith((".docx", ".doc")) and content[:2] == b"PK":
        safe = f"{Path(safe).stem}.docx"
    return safe or f"Tender_document{ext}"


def _pdf_save_name(doc: dict[str, str], pdf_bytes: bytes) -> str:
    """Backward-compatible alias."""
    return _tender_doc_save_name(doc, pdf_bytes)


def parse_file_list_html(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    docs: list[dict[str, str]] = []
    for row in soup.select("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        link = row.select_one('a[href*="file-download"]')
        if not link:
            continue
        href = link.get("href", "")
        docs.append(
            {
                "description": cells[1].get_text(" ", strip=True) if len(cells) > 1 else "",
                "filename": link.get_text(" ", strip=True) or cells[-1].get_text(" ", strip=True),
                "download_path": href,
            }
        )
    return docs


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, bool]:
    text = ""
    ocr_used = False
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            parts = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(parts).strip()
    except Exception as exc:
        logger.debug("pdfplumber failed: %s", exc)

    if len(text) >= 80:
        return text, ocr_used

    try:
        import fitz  # pymupdf

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        ocr_parts: list[str] = []
        for page in doc:
            page_text = page.get_text().strip()
            if page_text:
                ocr_parts.append(page_text)
            else:
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                try:
                    import pytesseract
                    from PIL import Image

                    img = Image.open(BytesIO(img_bytes))
                    ocr_parts.append(pytesseract.image_to_string(img))
                    ocr_used = True
                except Exception:
                    pass
        doc.close()
        combined = "\n".join(ocr_parts).strip()
        if len(combined) > len(text):
            text = combined
    except Exception as exc:
        logger.debug("pymupdf/OCR failed: %s", exc)

    return text, ocr_used


def parse_lot_lines_from_text(text: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    if not text:
        return lines
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) < 8:
            continue
        kg_match = re.search(r"(\d[\d,]*\.?\d*)\s*(?:kg|kgs|kilogram)", line, re.I)
        qty_match = re.search(r"\b(?:qty|quantity|no\.?)\s*[:\-]?\s*(\d[\d,]*)", line, re.I)
        if kg_match or (re.search(r"\b\d+\s", line) and re.search(r"scrap|blade|sheet|pipe|angle|bar|coil|wire|item", line, re.I)):
            lines.append(
                {
                    "raw_line": line,
                    "qty": qty_match.group(1) if qty_match else None,
                    "weight_kg": parse_emd_amount(kg_match.group(1)) if kg_match else None,
                }
            )
    return lines[:50]


def enrich_auction(
    client: GemForwardClient,
    listing: dict[str, Any],
    *,
    docs_dir: Path,
    delay: float,
) -> dict[str, Any]:
    auction_id = listing["auction_id"]
    record: dict[str, Any] = dict(listing)
    record["result_items"] = []
    record["opening_items"] = []
    record["documents"] = []
    record["lot_lines"] = []
    record["extraction_warnings"] = []

    if listing.get("result_path"):
        time.sleep(delay)
        result_html = client.get_html(listing["result_path"])
        record["result_items"] = parse_result_page(result_html)
        if not record["result_items"]:
            record["extraction_warnings"].append("empty_result_table")

    notice_path = listing.get("notice_path") or ""
    if not notice_path:
        record["extraction_warnings"].append("missing_notice_path")
        return record

    time.sleep(delay)
    notice_html = client.get_html(notice_path)
    detail = parse_detail_page(notice_html)
    record["category"] = detail.get("category")
    record["auction_brief"] = detail.get("auction_brief")
    record["auction_detail"] = detail.get("auction_detail")
    record["seller_name"] = detail.get("seller_name")
    record["emd_required"] = detail.get("emd_required")
    record["label_pairs"] = detail.get("label_pairs", {})

    emd_text = detail.get("label_pairs", {}).get("EMD Amount") or detail.get("label_pairs", {}).get("EMD")
    record["emd_amount_inr"] = parse_emd_amount(emd_text) if emd_text else None

    rules_path = detail.get("rules_path")
    if rules_path:
        time.sleep(delay)
        rules_html = client.get_html(rules_path)
        items = parse_rules_page(rules_html)
        record["opening_items"] = [i.model_dump() for i in items]
        record["min_opening_inr"] = min(
            (i.opening_price_inr for i in items if i.opening_price_inr is not None),
            default=None,
        )
    else:
        record["extraction_warnings"].append("missing_rules_page")

    file_list_path = find_file_list_url(notice_html, auction_id)
    if file_list_path:
        time.sleep(delay)
        try:
            file_list_html = client.get_html(file_list_path)
            docs_meta = parse_file_list_html(file_list_html)
            auction_docs_dir = docs_dir / str(auction_id)
            auction_docs_dir.mkdir(parents=True, exist_ok=True)
            for doc in docs_meta:
                dl_path = doc.get("download_path", "")
                if not dl_path:
                    continue
                time.sleep(delay)
                try:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(_download_binary, client, dl_path)
                        pdf_bytes = fut.result(timeout=75)
                    safe_name = _tender_doc_save_name(doc, pdf_bytes)
                    local_path = auction_docs_dir / safe_name
                    local_path.write_bytes(pdf_bytes)
                    if pdf_bytes[:4] == b"%PDF":
                        text, ocr_used = extract_pdf_text(pdf_bytes)
                        lot_lines = parse_lot_lines_from_text(text)
                    else:
                        text, ocr_used, lot_lines = "", False, []
                    record["lot_lines"].extend(lot_lines)
                    record["documents"].append(
                        {
                            **doc,
                            "local_path": repo_relative_path(local_path),
                            "text_length": len(text),
                            "ocr_used": ocr_used,
                            "extracted_text_preview": text[:4000],
                            "content_type": "pdf" if pdf_bytes[:4] == b"%PDF" else "office",
                            "lot_lines_found": len(lot_lines),
                    }
                    )
                except TimeoutError:
                    record["extraction_warnings"].append(f"doc_download_timeout:{doc.get('filename')}")
                except Exception as exc:
                    record["extraction_warnings"].append(f"doc_download_failed:{doc.get('filename')}:{exc}")
        except Exception as exc:
            record["extraction_warnings"].append(f"file_list_failed:{exc}")
    else:
        record["extraction_warnings"].append("no_file_list")

    # Premium calculation
    if record.get("result_items") and record.get("min_opening_inr"):
        for ri in record["result_items"]:
            bid = ri.get("winning_bid_inr")
            opening = record.get("min_opening_inr")
            if bid and opening and opening > 0:
                ri["premium_over_opening_pct"] = round((bid - opening) / opening * 100, 2)

    total_kg = sum(l.get("weight_kg") or 0 for l in record["lot_lines"])
    if total_kg > 0 and record.get("result_items"):
        bid = record["result_items"][0].get("winning_bid_inr")
        if bid:
            record["implied_inr_per_kg"] = round(bid / total_kg, 2)
            record["total_weight_kg_estimated"] = total_kg

    record["asset_category"] = normalize_gem_category(
        category=record.get("category"),
        title=record.get("title"),
    )
    return record


def _download_binary(client: GemForwardClient, path: str) -> bytes:
    """Download file bytes via client's transport (SSH fallback after direct fail)."""
    import os
    import shlex
    import subprocess

    import requests

    from scraper.config import (
        HOSTINGER_HOST,
        HOSTINGER_PORT,
        HOSTINGER_SSH_KEY,
        HOSTINGER_USERNAME,
        REQUEST_TIMEOUT,
        USER_AGENT,
    )

    def _via_ssh() -> bytes:
        url = client._absolute_url(path)
        ssh_key = os.path.expanduser(os.getenv("HOSTINGER_SSH_KEY", HOSTINGER_SSH_KEY).strip())
        host = os.getenv("HOSTINGER_HOST", HOSTINGER_HOST).strip()
        port = os.getenv("HOSTINGER_PORT", str(HOSTINGER_PORT)).strip()
        user = os.getenv("HOSTINGER_USERNAME", HOSTINGER_USERNAME).strip()
        cookie = "/tmp/gem_forward_cookies.txt"
        script = (
            f"curl -sL -m {REQUEST_TIMEOUT} -b {shlex.quote(cookie)} -c {shlex.quote(cookie)} "
            f"-A {shlex.quote(USER_AGENT)} {shlex.quote(url)}"
        )
        cmd = [
            "ssh",
            "-i",
            ssh_key,
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{user}@{host}",
            script,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=90)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout

    if client._active_transport == "ssh" or client._transport_mode == "ssh":
        return _via_ssh()

    url = client._absolute_url(path)
    try:
        resp = client._ensure_direct().get(url, timeout=60)
        resp.raise_for_status()
        client._active_transport = "direct"
        return resp.content
    except (requests.RequestException, OSError):
        client._active_transport = "ssh"
        return _via_ssh()


def fetch_pure_scrap_samples(
    *,
    limit: int = 50,
    transport: str = "ssh",
    max_pages: int = 500,
    docs_dir: Path,
    delay: float = GEM_FORWARD_REQUEST_DELAY_SEC,
    on_progress: Optional[Any] = None,
    skip_auction_ids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    client = GemForwardClient(transport=transport)
    client.init_session()

    collected: list[dict[str, Any]] = []
    scanned = 0
    skipped_not_scrap = 0
    skipped_no_winner = 0
    skipped_seen = 0
    seen = skip_auction_ids or set()

    for page in range(1, max_pages + 1):
        if len(collected) >= limit:
            break
        html = client.search_auctions_html(
            page=page,
            per_page=10,
            status=GEM_CLOSED_STATUS,
            category_id=GEM_SCRAP_CATEGORY_ID,
        )
        soup = BeautifulSoup(html, "lxml")
        blocks = soup.select("div.eproc-listing-main")
        if not blocks:
            break

        for block in blocks:
            if len(collected) >= limit:
                break
            listing = parse_listing_block(block)
            scanned += 1
            if not listing.get("auction_id") or not listing.get("result_path"):
                continue
            if listing["auction_id"] in seen:
                skipped_seen += 1
                continue
            if not is_pure_scrap_title(listing["title"]):
                skipped_not_scrap += 1
                continue

            time.sleep(delay)
            result_html = client.get_html(listing["result_path"])
            result_items = parse_result_page(result_html)
            if not result_items:
                skipped_no_winner += 1
                continue

            logger.info(
                "Enriching %s (%d/%d): %s",
                listing["auction_id"],
                len(collected) + 1,
                limit,
                listing["title"][:60],
            )
            record = enrich_auction(client, listing, docs_dir=docs_dir, delay=delay)
            record["result_items"] = result_items
            collected.append(record)
            if on_progress:
                on_progress(collected)

        if page % 20 == 0:
            logger.info(
                "Progress page=%d collected=%d scanned=%d skipped_scrap=%d skipped_no_winner=%d skipped_seen=%d",
                page, len(collected), scanned, skipped_not_scrap, skipped_no_winner, skipped_seen,
            )

    return collected


def generate_markdown_report(samples: list[dict[str, Any]], *, meta: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# GeM Forward — Pure Scrap Auction Results (Sample Analysis)")
    lines.append("")
    lines.append(f"**Generated:** {meta.get('generated_at', '')}")
    lines.append(f"**Sample size:** {len(samples)} closed auctions with winning bids")
    lines.append(f"**Source:** GeM Forward Auction (`forwardauction.gem.gov.in`), category General Scrap (ID 8)")
    lines.append(f"**Filter:** Pure scrap only — vehicles, ELV, demolition, grain, e-waste, machinery excluded")
    lines.append("")

    # Executive summary stats
    accepted = sum(
        1 for s in samples
        if any("accepted" in (r.get("acceptance_status") or "").lower() for r in s.get("result_items", []))
    )
    with_docs = sum(1 for s in samples if s.get("documents"))
    with_lot_lines = sum(1 for s in samples if s.get("lot_lines"))
    bids = [
        r.get("winning_bid_inr")
        for s in samples
        for r in s.get("result_items", [])
        if r.get("winning_bid_inr")
    ]
    openings = [s.get("min_opening_inr") for s in samples if s.get("min_opening_inr")]

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Auctions with winning bid data | {len(samples)} |")
    lines.append(f"| Accepted results | {accepted} |")
    lines.append(f"| Auctions with PDF documents | {with_docs} |")
    lines.append(f"| Auctions with lot-line extraction | {with_lot_lines} |")
    if bids:
        lines.append(f"| Winning bid range | {format_inr_amount(min(bids))} – {format_inr_amount(max(bids))} |")
        lines.append(f"| Median winning bid | {format_inr_amount(sorted(bids)[len(bids)//2])} |")
    if openings:
        lines.append(f"| Opening price range | {format_inr_amount(min(openings))} – {format_inr_amount(max(openings))} |")
    lines.append("")

    # State distribution
    states: dict[str, int] = {}
    for s in samples:
        st = s.get("state") or "Unknown"
        states[st] = states.get(st, 0) + 1
    lines.append("### Geographic Distribution")
    lines.append("")
    for st, cnt in sorted(states.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"- **{st}:** {cnt}")
    lines.append("")

    # Acceptance status breakdown
    status_counts: dict[str, int] = {}
    for s in samples:
        for r in s.get("result_items", []):
            st = r.get("acceptance_status") or "Unknown"
            status_counts[st] = status_counts.get(st, 0) + 1
    lines.append("### Acceptance Status Breakdown")
    lines.append("")
    for st, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {st}: {cnt}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Individual Auction Profiles")
    lines.append("")

    for i, s in enumerate(samples, 1):
        aid = s.get("auction_id", "?")
        lines.append(f"### {i}. Auction {aid} — {s.get('title', 'Untitled')}")
        lines.append("")
        lines.append("#### Identity & Location")
        lines.append("")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| Auction ID | {aid} |")
        lines.append(f"| Category (portal) | {s.get('category') or '—'} |")
        lines.append(f"| Asset category (normalized) | {s.get('asset_category') or '—'} |")
        lines.append(f"| Organisation | {' → '.join(s.get('organisation') or []) or '—'} |")
        lines.append(f"| Seller/Auctioneer | {s.get('seller_name') or '—'} |")
        loc = ", ".join(filter(None, [s.get("city"), s.get("district"), s.get("state"), s.get("pincode")]))
        lines.append(f"| Location | {loc or '—'} |")
        lines.append(f"| Auction window | {s.get('opening') or '—'} → {s.get('closing') or '—'} |")
        lines.append(f"| EMD required | {s.get('emd_required')} |")
        if s.get("emd_amount_inr"):
            lines.append(f"| EMD amount | {format_inr_amount(s['emd_amount_inr'])} |")
        lines.append("")

        lines.append("#### Auction Brief & Detail")
        lines.append("")
        if s.get("auction_brief"):
            lines.append(f"**Brief:** {s['auction_brief']}")
            lines.append("")
        if s.get("auction_detail"):
            lines.append(f"**Detail:** {s['auction_detail']}")
            lines.append("")

        lines.append("#### Pricing & Results")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|-------|-------|")
        if s.get("min_opening_inr"):
            lines.append(f"| Minimum opening price (rules) | {format_inr_amount(s['min_opening_inr'])} |")
        if s.get("total_weight_kg_estimated"):
            lines.append(f"| Estimated total weight (from PDF) | {s['total_weight_kg_estimated']:,.0f} kg |")
        if s.get("implied_inr_per_kg"):
            lines.append(f"| Implied ₹/kg (bid ÷ est. weight) | {format_inr_amount(s['implied_inr_per_kg'], decimals=2)}/kg |")
        lines.append("")

        if s.get("opening_items"):
            lines.append("**Opening prices (business rules):**")
            lines.append("")
            lines.append("| Sr | Item | Opening ₹ | Increment ₹ |")
            lines.append("|----|------|-----------|-------------|")
            for oi in s["opening_items"]:
                op = oi.get("opening_price_inr")
                inc = oi.get("increment_price_inr")
                lines.append(
                    f"| {oi.get('sr_no')} | {oi.get('item_name', '')[:50]} | "
                    f"{format_inr_or_dash(op) if op else '—'} | {format_inr_or_dash(inc) if inc else '—'} |"
                )
            lines.append("")

        if s.get("result_items"):
            lines.append("**Winning bids (H1):**")
            lines.append("")
            lines.append("| Sr | Item | Winning bidder | Bid ₹ | Bid time | Status | Premium % |")
            lines.append("|----|------|----------------|-------|----------|--------|-----------|")
            for ri in s["result_items"]:
                bid = ri.get("winning_bid_inr")
                prem = ri.get("premium_over_opening_pct")
                lines.append(
                    f"| {ri.get('sr_no')} | {(ri.get('item_name') or '')[:40]} | "
                    f"{ri.get('winning_bidder') or '—'} | "
                    f"{format_inr_amount(bid, decimals=2) if bid else ri.get('winning_bid_text', '—')} | "
                    f"{ri.get('bid_datetime') or '—'} | {ri.get('acceptance_status') or '—'} | "
                    f"{f'{prem:.1f}%' if prem is not None else '—'} |"
                )
            lines.append("")

        if s.get("lot_lines"):
            lines.append("#### Lot Contents (extracted from PDFs)")
            lines.append("")
            lines.append("| # | Line (from document) | Qty | Weight (kg) |")
            lines.append("|---|------------------------|-----|-------------|")
            for j, ll in enumerate(s["lot_lines"][:30], 1):
                lines.append(
                    f"| {j} | {ll.get('raw_line', '')[:80]} | "
                    f"{ll.get('qty') or '—'} | {ll.get('weight_kg') or '—'} |"
                )
            if len(s["lot_lines"]) > 30:
                lines.append(f"| … | *({len(s['lot_lines']) - 30} more lines)* | | |")
            lines.append("")

        if s.get("documents"):
            lines.append("#### Documents")
            lines.append("")
            for doc in s["documents"]:
                lines.append(f"- **{doc.get('description') or doc.get('filename')}**")
                lines.append(f"  - File: `{doc.get('local_path', '—')}`")
                lines.append(f"  - Text extracted: {doc.get('text_length', 0)} chars")
                lines.append(f"  - OCR used: {doc.get('ocr_used', False)}")
                lines.append(f"  - Lot lines parsed: {doc.get('lot_lines_found', 0)}")
                preview = (doc.get("extracted_text_preview") or "").strip()
                if preview:
                    lines.append("")
                    lines.append("<details>")
                    lines.append(f"<summary>Extracted text preview ({doc.get('filename')})</summary>")
                    lines.append("")
                    lines.append("```")
                    lines.append(preview[:2000])
                    lines.append("```")
                    lines.append("</details>")
                    lines.append("")
            lines.append("")

        if s.get("extraction_warnings"):
            lines.append("#### Extraction Notes")
            lines.append("")
            for w in s["extraction_warnings"]:
                lines.append(f"- ⚠ {w}")
            lines.append("")

        if s.get("result_path"):
            lines.append(f"**GeM result URL:** `https://forwardauction.gem.gov.in{s['result_path']}`")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Methodology & Limitations")
    lines.append("")
    lines.append("1. **Data source:** Public GeM Forward closed-auction listings (category General Scrap) with non-empty Auction Result tables.")
    lines.append("2. **Pure scrap filter:** Titles/categories matching scrap/metal/unserviceable keywords; excludes vehicles, ELV, demolition, grain, e-waste, machinery.")
    lines.append("3. **Lot contents:** Primarily from attached PDFs via text extraction; scanned documents may need OCR (Tesseract if available).")
    lines.append("4. **₹/kg implied price:** Only computed when weight lines could be parsed from PDFs — often incomplete for multi-material lots.")
    lines.append("5. **Acceptance status:** 'Pending Transaction Charge Payment' means bid won but sale not yet confirmed.")
    lines.append("6. **~76% of closed GeM auctions have empty result tables** — this report only covers auctions with published winners.")
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Fetch GeM pure scrap result samples")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--transport", default="ssh", choices=["auto", "direct", "ssh"])
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--delay", type=float, default=GEM_FORWARD_REQUEST_DELAY_SEC)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO_ROOT / "work" / "gem_scrap_samples.json",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=REPO_ROOT / "work" / "gem_scrap_samples_report.md",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from existing JSON out file")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=REPO_ROOT / "work" / "gem_scrap_docs",
    )
    args = parser.parse_args(argv)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.docs_dir.mkdir(parents=True, exist_ok=True)

    existing_samples: list[dict[str, Any]] = []
    if args.resume and args.json_out.exists():
        try:
            existing_samples = json.loads(args.json_out.read_text(encoding="utf-8")).get("samples", [])
            logger.info("Resuming with %d existing samples", len(existing_samples))
        except Exception as exc:
            logger.warning("Could not load resume file: %s", exc)

    def save_progress(samples: list[dict[str, Any]]) -> None:
        meta = {
            "generated_at": datetime.now(IST).isoformat(),
            "count": len(samples),
            "limit_requested": args.limit,
            "status": "in_progress" if len(samples) < args.limit else "complete",
        }
        payload = {"meta": meta, "samples": samples}
        args.json_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    samples: list[dict[str, Any]] = list(existing_samples)
    try:
        remaining = max(0, args.limit - len(samples))
        if remaining > 0:
            def progress_callback(batch: list[dict[str, Any]]) -> None:
                save_progress(samples + batch)

            new_samples = fetch_pure_scrap_samples(
                limit=remaining,
                transport=args.transport,
                max_pages=args.max_pages,
                docs_dir=args.docs_dir,
                delay=args.delay,
                on_progress=progress_callback,
                skip_auction_ids={s["auction_id"] for s in samples if s.get("auction_id")},
            )
            samples.extend(new_samples)
    except GemForwardTransportError as exc:
        logger.error("Transport failed: %s", exc)
        if not samples:
            return 1
        logger.warning("Generating report from %d partial samples", len(samples))

    meta = {
        "generated_at": datetime.now(IST).isoformat(),
        "count": len(samples),
        "limit_requested": args.limit,
    }
    payload = {"meta": meta, "samples": samples}
    args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("Wrote JSON: %s (%d samples)", args.json_out, len(samples))

    report = generate_markdown_report(samples, meta=meta)
    args.md_out.write_text(report, encoding="utf-8")
    logger.info("Wrote report: %s", args.md_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
