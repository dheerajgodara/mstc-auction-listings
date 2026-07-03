from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from scraper.eauction_client import EAUCTION_BASE

IST = ZoneInfo("Asia/Kolkata")

_INR_RE = re.compile(r"[\d,]+(?:\.\d+)?")
_HEADER_ALIASES = {
    "s.no": "sno",
    "sr.no": "sno",
    "auction id": "auction_id",
    "title": "title",
    "publish date": "publish_date",
    "closing date": "closing_date",
    "view": "view",
}


def _parse_inr(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    match = _INR_RE.search(value.replace("Rs.", "").replace("INR", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value.strip())
    for fmt in (
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%b-%Y %I:%M %p",
        "%d-%b-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _header_map(table) -> dict[int, str]:
    mapping: dict[int, str] = {}
    header_row = table.find("tr", class_=re.compile("list_header")) or table.find("thead")
    if header_row is None:
        first = table.find("tr")
        header_row = first
    if header_row is None:
        return mapping
    for idx, cell in enumerate(header_row.find_all(["td", "th"])):
        label = cell.get_text(" ", strip=True).lower()
        mapping[idx] = _HEADER_ALIASES.get(label, label.replace(" ", "_"))
    return mapping


def _extract_view_url(tr) -> Optional[str]:
    for anchor in tr.find_all("a", href=True):
        href = anchor["href"]
        if "component=view" in href or "ViewAuction" in href:
            return urljoin(EAUCTION_BASE, href)
    return None


def parse_listing_rows(html: str) -> list[dict[str, Any]]:
    """Parse eAuction closing-date listing tables (6-column public layout)."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        headers = _header_map(table)
        if headers and "auction_id" not in headers.values() and "title" not in headers.values():
            continue

        for tr in table.find_all("tr"):
            if tr.find("td", class_="list_footer"):
                continue
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue

            values = [c.get_text(" ", strip=True) for c in cells]
            if not values[0] or values[0].lower() in {"s.no", "sr.no"}:
                continue
            if not re.match(r"\d", values[0]) and not re.search(r"\d{4}_[A-Z]{2}_\d+", values[1] if len(values) > 1 else ""):
                continue

            record: dict[str, Any] = {
                "auction_id": None,
                "title": None,
                "organisation": None,
                "product_category": None,
                "sub_category": None,
                "publish_date": None,
                "closing_date": None,
                "starting_price_inr": None,
                "reserve_price_inr": None,
                "emd_inr": None,
                "increment_inr": None,
                "location": None,
                "detail_url": _extract_view_url(tr),
                "document_urls": [],
            }

            if headers:
                for idx, key in headers.items():
                    if idx >= len(values):
                        continue
                    val = values[idx] or None
                    if key == "auction_id":
                        record["auction_id"] = val
                    elif key == "title":
                        record["title"] = val
                    elif key == "publish_date":
                        record["publish_date"] = _parse_date(val)
                    elif key == "closing_date":
                        record["closing_date"] = _parse_date(val)
            else:
                if len(values) >= 6:
                    record["auction_id"] = values[1]
                    record["title"] = values[2]
                    record["publish_date"] = _parse_date(values[3])
                    record["closing_date"] = _parse_date(values[4])
                elif len(values) >= 4:
                    record["auction_id"] = values[1] if len(values) > 1 else values[0]
                    record["title"] = values[2] if len(values) > 2 else values[1]

            if not record["auction_id"]:
                record["auction_id"] = re.sub(r"\W+", "", values[1] if len(values) > 1 else values[0])[:32]
            if not record["title"]:
                record["title"] = values[2] if len(values) > 2 else values[0]

            rows.append(record)

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = f"{row.get('auction_id')}::{row.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def parse_detail_page(html: str, base_record: dict[str, Any]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    record = dict(base_record)
    document_urls = list(record.get("document_urls") or [])

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        label = anchor.get_text(" ", strip=True).lower()
        if any(token in label for token in ("document", "pdf", "download", "annex", "brochure")):
            full = urljoin(EAUCTION_BASE, href)
            if full not in document_urls:
                document_urls.append(full)
        if href.lower().endswith(".pdf"):
            full = urljoin(EAUCTION_BASE, href)
            if full not in document_urls:
                document_urls.append(full)

    field_map = {
        "auction id": "auction_id",
        "auction title": "title",
        "organisation chain": "organisation",
        "organization chain": "organisation",
        "product category": "product_category",
        "sub category": "sub_category",
        "sub-category": "sub_category",
        "location": "location",
        "state": "state",
        "publish date": "publish_date",
        "closing date": "closing_date",
        "start price": "starting_price_inr",
        "starting price": "starting_price_inr",
        "reserve price": "reserve_price_inr",
        "emd amount": "emd_inr",
        "emd": "emd_inr",
        "increment": "increment_inr",
        "bid increment": "increment_inr",
    }

    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).lower()
        value = cells[1].get_text(" ", strip=True)
        if not value:
            continue
        for needle, field in field_map.items():
            if needle in label:
                if field in {"starting_price_inr", "reserve_price_inr", "emd_inr", "increment_inr"}:
                    record[field] = _parse_inr(value)
                elif field in {"publish_date", "closing_date"}:
                    record[field] = _parse_date(value) or record.get(field)
                else:
                    record[field] = value
                break

    if record.get("title") and not record.get("product_category"):
        desc = soup.find(string=re.compile("Product Category", re.I))
        if desc:
            pass

    record["document_urls"] = document_urls
    return record
