from __future__ import annotations

import logging
from pathlib import Path

import requests

from scraper.config import PDF_DETAIL_URL, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

MIN_PDF_BYTES = 1000


def download_pdf(auction_id: str, output_path: Path) -> Path:
    """Download auction catalogue PDF. Validates response is a real PDF."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.post(
        PDF_DETAIL_URL,
        data={"auc": auction_id},
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://www.mstcindia.co.in/",
            "Accept": "application/pdf,*/*",
        },
    )
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").lower()
    is_pdf = "pdf" in content_type or resp.content[:4] == b"%PDF"
    if not is_pdf:
        raise ValueError(
            f"Expected PDF for auction {auction_id}, got content-type={content_type!r}"
        )
    if len(resp.content) < MIN_PDF_BYTES:
        raise ValueError(
            f"PDF too small for auction {auction_id}: {len(resp.content)} bytes"
        )

    output_path.write_bytes(resp.content)
    logger.info("Saved PDF %s (%d bytes)", output_path.name, len(resp.content))
    return output_path
