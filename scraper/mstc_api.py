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


def fetch_office_auctions(
    office_code: str,
    session: requests.Session | None = None,
    *,
    attempts: int = 4,
    timeout: float | tuple[float, float] = (10, 60),
) -> ListingApiOfficeResponse:
    """Fetch auctions for a single regional office.

    Retries transient network timeouts/connection errors with backoff — GitHub
    Actions runners often see intermittent ReadTimeout against mstcindia.co.in.
    """
    sess = session or _session()
    url = f"{MSTC_BASE_URL}{LISTING_API_PATH.format(office=office_code)}"
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            resp = sess.get(url, timeout=timeout if timeout is not None else REQUEST_TIMEOUT)
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
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            delay = min(2 ** attempt, 20) + (attempt * 0.5)
            logger.warning(
                "MSTC office %s attempt %d/%d failed (%s); retrying in %.1fs",
                office_code,
                attempt,
                attempts,
                type(exc).__name__,
                delay,
            )
            time.sleep(delay)
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status = getattr(exc.response, "status_code", None)
            if status is None or status < 500 or attempt >= attempts:
                raise
            delay = min(2 ** attempt, 20)
            logger.warning(
                "MSTC office %s HTTP %s on attempt %d/%d; retrying in %.1fs",
                office_code,
                status,
                attempt,
                attempts,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


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
