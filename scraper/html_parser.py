from __future__ import annotations

import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from scraper.config import HTML_DETAIL_PATH, MSTC_BASE_URL, REQUEST_TIMEOUT, USER_AGENT
from scraper.emd import classify_emd_type_text, parse_emd_amount

logger = logging.getLogger(__name__)

FIELD_IDS = {
    "auction_number": "ContentPlaceHolder1_lblAuctionNo",
    "opening_raw": "ContentPlaceHolder1_lblOpeningDateTime",
    "closing_raw": "ContentPlaceHolder1_lblCloseAt",
    "inspection_from": "ContentPlaceHolder1_lblInspectionFromDate",
    "inspection_to": "ContentPlaceHolder1_lblInspectionClosingDate",
    "pre_bid_emd_type": "ContentPlaceHolder1_lblEmdType",
    "pre_bid_emd_amount_raw": "ContentPlaceHolder1_lblEmdAmt",
    "seller": "ContentPlaceHolder1_lblSellerName",
    "location": "ContentPlaceHolder1_lblLocation",
    "street": "ContentPlaceHolder1_lblStreet",
    "city": "ContentPlaceHolder1_lblCity",
    "country": "ContentPlaceHolder1_lblCountry",
    "telephone": "ContentPlaceHolder1_lblTelephone",
    "email": "ContentPlaceHolder1_lblEmail",
    "contact_person": "ContentPlaceHolder1_lblContactPerson",
    "total_lots": "ContentPlaceHolder1_lblTotalLotNo",
}


def _text(soup: BeautifulSoup, element_id: str) -> str | None:
    el = soup.find(id=element_id)
    if not el:
        return None
    text = el.get_text(" ", strip=True)
    return text or None


def _clean_description(raw: str | None) -> str | None:
    if not raw:
        return None
    text = BeautifulSoup(raw, "lxml").get_text(" ", strip=True) if "<" in raw else raw
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _parse_contact_from_description(raw: str) -> tuple[str | None, dict[str, Any] | None]:
    if not raw:
        return raw, None
    m = re.search(r"contact\s+details\s*[-:]\s*(.+)$", raw, re.I)
    if not m:
        return raw, None
    blob = m.group(1).strip()
    cleaned = raw[: m.start()].strip()
    phones = re.findall(r"(?:\+91[\-\s]?)?[6-9]\d{9}|\d{10,11}", blob)
    name = re.sub(r"[\d,]+", "", blob).strip(" ,;-")
    contact = {"name": name or None, "phones": list(dict.fromkeys(phones)), "email": None}
    return _clean_description(cleaned), contact


def _parse_lots(soup: BeautifulSoup) -> list[dict[str, Any]]:
    lots: list[dict[str, Any]] = []
    for i in range(200):
        lot_no = _text(soup, f"ContentPlaceHolder1_dgLot_lblNo_{i}")
        if not lot_no:
            break
        name = _text(soup, f"ContentPlaceHolder1_dgLot_lblName_{i}") or ""
        desc_el = soup.find(id=f"ContentPlaceHolder1_dgLot_lblLotDesc_{i}")
        raw_desc = str(desc_el) if desc_el else None
        description = _clean_description(desc_el.get_text(" ", strip=True) if desc_el else None)
        lot_contact = None
        if description:
            description, lot_contact = _parse_contact_from_description(description)

        qty = _text(soup, f"ContentPlaceHolder1_dgLot_lblQuantity_{i}")
        unit = _text(soup, f"ContentPlaceHolder1_dgLot_Label4_{i}")
        ed = _text(soup, f"ContentPlaceHolder1_dgLot_lblED_{i}")
        gst = _text(soup, f"ContentPlaceHolder1_dgLot_sales_tax_{i}")
        tax_parts = [p for p in [ed, gst] if p]
        tax_text = " / ".join(tax_parts) if tax_parts else None
        location = _text(soup, f"ContentPlaceHolder1_dgLot_lblPlace_{i}")

        lot: dict[str, Any] = {
            "lot_no": lot_no,
            "name": name,
            "description": description,
            "quantity": qty,
            "unit": unit,
            "tax_text": tax_text,
            "location": location,
        }
        if lot_contact:
            lot["inspection_contact"] = lot_contact
        lots.append(lot)
    return lots


def fetch_html_detail(auction_id: str) -> str:
    """Fetch MSTC HTML detail; 1–2 short retries on timeout/connection only."""
    import time

    url = f"{MSTC_BASE_URL}{HTML_DETAIL_PATH.format(auction_id=auction_id)}"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    # (connect, read) — fail connect fast; HTML bodies are small.
    timeout = (10, float(REQUEST_TIMEOUT))
    last_exc: Exception | None = None
    for attempt in range(1, 3):
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
            return resp.text
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt >= 2:
                break
            time.sleep(0.4 * attempt)
            logger.warning(
                "HTML detail %s attempt %d/2 failed (%s); retry",
                auction_id,
                attempt,
                exc,
            )
    assert last_exc is not None
    raise last_exc


def parse_html_detail(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    data = {key: _text(soup, eid) for key, eid in FIELD_IDS.items()}

    phones: list[str] = []
    if data.get("telephone"):
        phones = re.findall(r"\d{10,11}", data["telephone"].replace(" ", ""))
        if not phones:
            phones = [p.strip() for p in data["telephone"].split(",") if p.strip()]

    seller_contact = {
        "name": data.get("contact_person"),
        "phones": phones,
        "email": data.get("email"),
    }

    emd_type_raw = data.get("pre_bid_emd_type")
    emd_amount = parse_emd_amount(data.get("pre_bid_emd_amount_raw"))
    emd_required, emd_status = classify_emd_type_text(emd_type_raw)
    if emd_status == "auction_wise" and emd_amount is not None:
        pass
    elif emd_status == "item_wise":
        pass
    elif emd_status == "not_required":
        emd_amount = emd_amount if emd_amount is not None else None

    street = data.get("street")
    city = data.get("city")
    office_address = ", ".join(p for p in [street, city] if p) or None

    return {
        "auction_number": data.get("auction_number"),
        "opening_raw": data.get("opening_raw"),
        "closing_raw": data.get("closing_raw"),
        "inspection_from": data.get("inspection_from"),
        "inspection_to": data.get("inspection_to"),
        "pre_bid_emd_type": emd_type_raw,
        "pre_bid_emd_amount": emd_amount,
        "pre_bid_emd_required": emd_required,
        "emd_parse_status": emd_status,
        "seller": data.get("seller"),
        "location": data.get("location"),
        "office_address": office_address,
        "country": data.get("country"),
        "seller_contact": seller_contact,
        "contact": seller_contact,
        "total_lots": data.get("total_lots"),
        "lots": _parse_lots(soup),
        "mstc_html_url": None,
    }


def fetch_and_parse_html_detail(auction_id: str) -> dict[str, Any]:
    url = f"{MSTC_BASE_URL}{HTML_DETAIL_PATH.format(auction_id=auction_id)}"
    html = fetch_html_detail(auction_id)
    parsed = parse_html_detail(html)
    parsed["mstc_html_url"] = url
    logger.info("Parsed HTML for %s: %d lots", auction_id, len(parsed.get("lots", [])))
    return parsed
