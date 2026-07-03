from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from scraper.config import (
    LISTING_API_PATH,
    MSTC_BASE_URL,
    OFFICE_CODES,
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from scraper.models import ListingApiAuction, ListingApiOfficeResponse

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def parse_mstc_datetime(value: str) -> datetime | None:
    """Parse MSTC date strings like DD-MM-YYYY::HH:MM:SS."""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%d-%m-%Y::%H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=IST)
        except ValueError:
            continue
    logger.warning("Could not parse datetime: %s", value)
    return None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def fetch_office_auctions(office_code: str, session: requests.Session | None = None) -> ListingApiOfficeResponse:
    """Fetch auctions for a single regional office."""
    sess = session or _session()
    url = f"{MSTC_BASE_URL}{LISTING_API_PATH.format(office=office_code)}"
    resp = sess.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise ValueError(f"Unexpected API response for office {office_code}")
    payload: dict[str, Any] = data[0]
    auctions = [ListingApiAuction.model_validate(a) for a in payload.get("auction", [])]
    return ListingApiOfficeResponse(
        MSG=payload.get("MSG", ""),
        OFFICE=payload.get("OFFICE", office_code),
        REGION=payload.get("REGION", office_code),
        auction=auctions,
    )


def fetch_all_listing_api(
    office_codes: list[str] | None = None,
    delay_sec: float = REQUEST_DELAY_SEC,
) -> list[tuple[ListingApiOfficeResponse, list[ListingApiAuction]]]:
    """Fetch listing API for all offices. Returns (office_meta, auctions) pairs."""
    codes = office_codes or OFFICE_CODES
    sess = _session()
    results: list[tuple[ListingApiOfficeResponse, list[ListingApiAuction]]] = []

    for i, code in enumerate(codes):
        try:
            office = fetch_office_auctions(code, session=sess)
            results.append((office, office.auction))
            logger.info("Fetched %s: %d auctions", code, len(office.auction))
        except Exception as exc:
            logger.error("Failed to fetch office %s: %s", code, exc)
        if i < len(codes) - 1 and delay_sec > 0:
            time.sleep(delay_sec)

    return results


def lot_types_from_flags(general: str, rvsf: str, hazardous: str) -> list[str]:
    types: list[str] = []
    if general == "Yes":
        types.append("General")
    if rvsf == "Yes":
        types.append("RVSF")
    if hazardous == "Yes":
        types.append("Hazardous")
    return types
