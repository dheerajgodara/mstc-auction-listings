"""Optional Cloudflare R2 / S3-compatible durable object store for auction PDFs.

When R2_* env vars are set, publish lane uploads here first (HTTP API with timeouts),
then mirrors to Hostinger for the live site. When unset, Hostinger remains the only store.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from scraper.config import (
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET,
    R2_ENDPOINT_URL,
    R2_PUBLIC_BASE_URL,
    R2_SECRET_ACCESS_KEY,
)

logger = logging.getLogger("scraper.object_store")


def r2_configured() -> bool:
    if R2_BUCKET and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
        return True
    return False


def r2_endpoint() -> str:
    if R2_ENDPOINT_URL:
        return R2_ENDPOINT_URL.rstrip("/")
    if R2_ACCOUNT_ID:
        return f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return ""


def public_object_url(key: str) -> str | None:
    base = (R2_PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return None
    return f"{base}/{key.lstrip('/')}"


def upload_file(
    local_path: Path,
    *,
    key: str,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Upload a local file to R2. Returns {ok, url?, error?, key}."""
    path = Path(local_path)
    if not path.is_file():
        return {"ok": False, "key": key, "error": "local file missing"}
    if not r2_configured():
        return {"ok": False, "key": key, "error": "R2 not configured"}

    endpoint = r2_endpoint()
    if not endpoint:
        return {"ok": False, "key": key, "error": "R2 endpoint missing"}

    ctype = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        return {
            "ok": False,
            "key": key,
            "error": "boto3 not installed — pip install boto3 for R2 uploads",
        }

    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=BotoConfig(
                connect_timeout=15,
                read_timeout=120,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        extra = {"ContentType": ctype, "ACL": "public-read"}
        client.upload_file(str(path), R2_BUCKET, key.lstrip("/"), ExtraArgs=extra)
        url = public_object_url(key)
        logger.info("R2 upload ok key=%s bytes=%s", key, path.stat().st_size)
        return {"ok": True, "key": key, "url": url, "bucket": R2_BUCKET}
    except Exception as exc:
        logger.warning("R2 upload failed key=%s: %s", key, exc)
        return {"ok": False, "key": key, "error": str(exc)}


def upload_hostinger_rel(local_path: Path, hostinger_doc_path: str) -> dict[str, Any]:
    """Upload using Hostinger-relative path as object key (pdfs/… or docs/gem/…)."""
    key = str(hostinger_doc_path).lstrip("/")
    return upload_file(local_path, key=key)
