from __future__ import annotations

import logging
import os
import random
import tempfile
import time
from pathlib import Path

import requests

from scraper.config import PDF_DETAIL_URL, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

MIN_PDF_BYTES = 1000

# MSTC's catalogue endpoint is intermittently 500. Retries + backoff recover most.
DEFAULT_PDF_RETRIES = 5
DEFAULT_PDF_BACKOFF_BASE_SEC = 2.0
DEFAULT_PDF_BACKOFF_CAP_SEC = 45.0


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


def _is_retryable_http(status: int) -> bool:
    return status in {408, 425, 429, 500, 502, 503, 504}


def _fetch_pdf_bytes(
    auction_id: str,
    *,
    session: requests.Session | None = None,
    timeout: float | None = None,
) -> bytes:
    """Single attempt POST to MSTC catalogue PDF endpoint."""
    sess = session or requests
    resp = sess.post(
        PDF_DETAIL_URL,
        data={"auc": auction_id},
        timeout=timeout if timeout is not None else REQUEST_TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://www.mstcindia.co.in/",
            "Accept": "application/pdf,*/*",
        },
    )
    if _is_retryable_http(resp.status_code):
        raise requests.HTTPError(
            f"{resp.status_code} Server Error for url: {resp.url}",
            response=resp,
        )
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").lower()
    body = resp.content
    is_pdf = "pdf" in content_type or body[:4] == b"%PDF"
    if not is_pdf or not is_valid_pdf_bytes(body):
        # MSTC sometimes returns 200 HTML error pages — treat as retryable soft fail.
        preview = body[:80].decode("utf-8", errors="replace").lower()
        if "<html" in preview or "error 500" in preview:
            raise requests.HTTPError(
                f"MSTC returned HTML error page instead of PDF for {auction_id}",
                response=resp,
            )
        raise ValueError(
            f"Expected PDF for auction {auction_id}, got content-type={content_type!r} "
            f"bytes={len(body)}"
        )
    return body


def download_pdf(
    auction_id: str,
    output_path: Path,
    *,
    retries: int = DEFAULT_PDF_RETRIES,
    backoff_base_sec: float = DEFAULT_PDF_BACKOFF_BASE_SEC,
    backoff_cap_sec: float = DEFAULT_PDF_BACKOFF_CAP_SEC,
    session: requests.Session | None = None,
) -> Path:
    """Download auction catalogue PDF with retries for MSTC flakiness.

    Retries on 5xx/429/timeouts and HTML error bodies. Uses exponential backoff
    with jitter. Validates response is a real PDF before writing.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    attempts = max(1, int(retries))
    last_exc: Exception | None = None
    own_session = session is None
    sess = session or requests.Session()

    try:
        for attempt in range(1, attempts + 1):
            try:
                content = _fetch_pdf_bytes(auction_id, session=sess)
                break
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError, requests.HTTPError))
                if isinstance(exc, requests.HTTPError):
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    retryable = status is None or _is_retryable_http(int(status)) or "HTML error" in str(exc)
                if isinstance(exc, ValueError) and "Expected PDF" in str(exc):
                    retryable = True
                if not retryable or attempt >= attempts:
                    raise
                delay = min(backoff_cap_sec, backoff_base_sec * (2 ** (attempt - 1)))
                delay *= 0.75 + random.random() * 0.5  # jitter
                logger.warning(
                    "MSTC PDF %s attempt %d/%d failed (%s); retry in %.1fs",
                    auction_id,
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
        else:
            assert last_exc is not None
            raise last_exc

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{auction_id}.", suffix=".pdf.part", dir=output_path.parent
        )
        tmp_path = Path(tmp_name)
        try:
            with open(fd, "wb") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            tmp_path.replace(output_path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    finally:
        if own_session:
            close = getattr(sess, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    logger.info("Saved PDF %s (%d bytes)", output_path.name, len(content))
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
