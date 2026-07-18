from __future__ import annotations

import logging
from pathlib import Path

import requests

from scraper.config import PDF_DETAIL_URL, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

MIN_PDF_BYTES = 1000


def is_valid_pdf_bytes(content: bytes) -> bool:
    return bool(content) and content[:4] == b"%PDF" and len(content) >= MIN_PDF_BYTES


def validate_pdf_file(path: Path) -> bool:
    """True when path exists and looks like a real catalogue PDF."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        size = path.stat().st_size
        if size < MIN_PDF_BYTES:
            return False
        with path.open("rb") as fh:
            magic = fh.read(4)
        return magic == b"%PDF"
    except OSError:
        return False


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
    if not is_pdf or not is_valid_pdf_bytes(resp.content):
        raise ValueError(
            f"Expected PDF for auction {auction_id}, got content-type={content_type!r} "
            f"bytes={len(resp.content)}"
        )

    output_path.write_bytes(resp.content)
    logger.info("Saved PDF %s (%d bytes)", output_path.name, len(resp.content))
    return output_path


def ensure_catalogue_pdf(
    auction_id: str,
    pdf_dir: Path,
    *,
    force_redownload: bool = False,
) -> tuple[Path, bool]:
    """Ensure ``pdf_dir/{id}.pdf`` exists and is a valid PDF.

    Returns ``(path, downloaded)`` where ``downloaded`` is True when a network
    fetch was performed (False on validated cache hit).

    Invalid/corrupt cached files are deleted and re-fetched.
    """
    pdf_dir = Path(pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{auction_id}.pdf"

    if not force_redownload and validate_pdf_file(pdf_path):
        return pdf_path, False

    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except OSError as exc:
            logger.warning("Could not remove invalid PDF cache %s: %s", pdf_path, exc)

    download_pdf(auction_id, pdf_path)
    if not validate_pdf_file(pdf_path):
        raise ValueError(f"PDF validation failed after download for auction {auction_id}")
    return pdf_path, True
