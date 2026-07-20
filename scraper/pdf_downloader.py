"""MSTC catalogue PDF fetch with antiflake tactics (proven on VPS experiment).

Evidence (`/opt/mstc-pdf-experiment`):
- Healthy: ~0.2–0.35s/PDF with batch=2 / 2s gap
- Flake mode: HTTP 500 HTML pages from mstcecommerce.com
- What recovered IDs: Edge-first UA rotation, fresh Session per attempt,
  Cache-Control bypass, cool-down between attempts
"""

from __future__ import annotations

import logging
import os
import random
import tempfile
import time
from pathlib import Path

import requests

from scraper.config import PDF_DETAIL_URL, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

MIN_PDF_BYTES = 1000

# Experiment order: Edge first (probe: Edge 200 while Chrome/Firefox 500).
MSTC_PDF_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
)

DEFAULT_PDF_RETRIES = int(os.environ.get("MSTC_PDF_RETRIES", "3"))
DEFAULT_PDF_BACKOFF_BASE_SEC = float(os.environ.get("MSTC_PDF_BACKOFF_BASE_SEC", "2.0"))
DEFAULT_PDF_BACKOFF_CAP_SEC = float(os.environ.get("MSTC_PDF_BACKOFF_CAP_SEC", "15.0"))


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


def _ua_label(ua: str) -> str:
    if "Edg/" in ua:
        return "edge"
    if "Firefox" in ua:
        return "firefox"
    if "Safari/" in ua and "Chrome" not in ua:
        return "safari"
    return "chrome"


def _antiflake_headers(ua: str) -> dict[str, str]:
    return {
        "User-Agent": ua,
        "Referer": "https://www.mstcindia.co.in/",
        "Origin": "https://www.mstcindia.co.in",
        "Accept": "application/pdf,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache, no-store",
        "Pragma": "no-cache",
        "Connection": "close",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _fetch_pdf_bytes(
    auction_id: str,
    *,
    user_agent: str,
    timeout: float | None = None,
) -> bytes:
    """Single attempt: fresh Session + Edge-class headers + cache-buster URL."""
    url = (
        f"{PDF_DETAIL_URL}"
        f"?_={int(time.time() * 1000)}&r={random.randint(1000, 9999)}"
    )
    sess = requests.Session()
    try:
        resp = sess.post(
            url,
            data={"auc": auction_id},
            timeout=timeout if timeout is not None else REQUEST_TIMEOUT,
            headers=_antiflake_headers(user_agent),
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
    finally:
        try:
            sess.close()
        except Exception:
            pass


def download_pdf(
    auction_id: str,
    output_path: Path,
    *,
    retries: int = DEFAULT_PDF_RETRIES,
    backoff_base_sec: float = DEFAULT_PDF_BACKOFF_BASE_SEC,
    backoff_cap_sec: float = DEFAULT_PDF_BACKOFF_CAP_SEC,
    session: requests.Session | None = None,
) -> Path:
    """Download catalogue PDF with Edge-first UA rotation and fresh sessions.

    ``session`` is ignored (kept for API compat); each attempt uses a new Session
    so cookies/TLS state from a 500 storm cannot poison the next try.
    """
    _ = session
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    attempts = max(1, int(retries))
    uas = list(MSTC_PDF_USER_AGENTS)
    last_exc: Exception | None = None
    content: bytes | None = None

    for attempt in range(1, attempts + 1):
        ua = uas[(attempt - 1) % len(uas)]
        label = _ua_label(ua)
        try:
            content = _fetch_pdf_bytes(auction_id, user_agent=ua)
            logger.info(
                "MSTC PDF %s ok via ua=%s attempt=%d/%d bytes=%d",
                auction_id,
                label,
                attempt,
                attempts,
                len(content),
            )
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
            delay = min(backoff_cap_sec, backoff_base_sec * attempt)
            delay += random.uniform(0.5, 1.5)
            logger.warning(
                "MSTC PDF %s attempt %d/%d ua=%s failed (%s); retry in %.1fs",
                auction_id,
                attempt,
                attempts,
                label,
                exc,
                delay,
            )
            time.sleep(delay)
    else:
        assert last_exc is not None
        raise last_exc

    assert content is not None
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
