"""Cloudflare R2 durable object store — canonical public media for PDFs/docs/thumbs.

With MEDIA_R2_ONLY=1 (default), download/publish/parse use R2 + R2_PUBLIC_BASE_URL
(files.scrapauctionindia.com). Hostinger is not used for media durability.
"""

from __future__ import annotations

import logging
import mimetypes
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from scraper.config import (
    MEDIA_R2_ONLY,
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET,
    R2_ENDPOINT_URL,
    R2_PUBLIC_BASE_URL,
    R2_SECRET_ACCESS_KEY,
)

logger = logging.getLogger("scraper.object_store")


def r2_configured() -> bool:
    return bool(R2_BUCKET and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)


def media_cdn_base() -> str:
    return (R2_PUBLIC_BASE_URL or "").rstrip("/")


def media_r2_only() -> bool:
    """True when media must be durable on R2 (no Hostinger media mirror required)."""
    return bool(MEDIA_R2_ONLY and r2_configured() and media_cdn_base())


def r2_endpoint() -> str:
    if R2_ENDPOINT_URL:
        return R2_ENDPOINT_URL.rstrip("/")
    if R2_ACCOUNT_ID:
        return f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return ""


def public_object_url(key: str) -> str | None:
    base = media_cdn_base()
    if not base:
        return None
    return f"{base}/{str(key).lstrip('/')}"


def media_key_from_url(url: str) -> str | None:
    """Extract pdfs|docs|thumbs relative key from a CDN or site URL."""
    raw = (url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        rel = raw.lstrip("/")
        if rel.startswith(("pdfs/", "docs/", "thumbs/")):
            return rel
        return None
    try:
        path = urlparse(raw).path.lstrip("/")
    except Exception:
        return None
    # Strip optional auctions/ prefix from legacy Hostinger URLs.
    if path.startswith("auctions/"):
        path = path[len("auctions/") :]
    if path.startswith(("pdfs/", "docs/", "thumbs/")):
        return path
    return None


def _s3_client():
    import boto3
    from botocore.config import Config as BotoConfig

    endpoint = r2_endpoint()
    if not endpoint:
        raise RuntimeError("R2 endpoint missing")
    return boto3.client(
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
        client = _s3_client()
        # Custom-domain buckets do not need ACL; omit if it fails on some tokens.
        extra: dict[str, Any] = {"ContentType": ctype}
        try:
            client.upload_file(str(path), R2_BUCKET, key.lstrip("/"), ExtraArgs=extra)
        except Exception:
            extra["ACL"] = "public-read"
            client.upload_file(str(path), R2_BUCKET, key.lstrip("/"), ExtraArgs=extra)
        url = public_object_url(key)
        logger.info("R2 upload ok key=%s bytes=%s", key, path.stat().st_size)
        return {"ok": True, "key": key.lstrip("/"), "url": url, "bucket": R2_BUCKET}
    except Exception as exc:
        logger.warning("R2 upload failed key=%s: %s", key, exc)
        return {"ok": False, "key": key, "error": str(exc)}


def upload_hostinger_rel(local_path: Path, hostinger_doc_path: str) -> dict[str, Any]:
    """Upload using relative media key as object key (pdfs/…, docs/…, thumbs/…)."""
    key = str(hostinger_doc_path).lstrip("/")
    return upload_file(local_path, key=key)


def verify_public_object_url(
    url: str,
    *,
    timeout_sec: float = 30.0,
    sniff_magic: bool = False,
) -> bool:
    """Return True when the public CDN URL responds with HTTP 200 (or 206)."""
    u = (url or "").strip()
    if not u:
        return False
    try:
        if sniff_magic or "/docs/gem/" in u:
            resp = requests.get(
                u,
                timeout=timeout_sec,
                allow_redirects=True,
                headers={
                    "Range": "bytes=0-4095",
                    "User-Agent": "Mozilla/5.0 MSTC-MediaVerify/1.0",
                },
            )
            if resp.status_code not in (200, 206):
                resp.close()
                return False
            from scraper.gem_doc_validate import is_gem_document_bytes

            ok, _kind, _err = is_gem_document_bytes(resp.content)
            resp.close()
            return ok

        headers = {"User-Agent": "Mozilla/5.0 MSTC-MediaVerify/1.0"}
        resp = requests.head(u, timeout=timeout_sec, allow_redirects=True, headers=headers)
        if resp.status_code == 200:
            return True
        if resp.status_code in (403, 405, 501):
            resp = requests.get(
                u,
                timeout=timeout_sec,
                allow_redirects=True,
                stream=True,
                headers={**headers, "Range": "bytes=0-0"},
            )
            ok = resp.status_code in (200, 206)
            resp.close()
            return ok
        resp = requests.get(
            u,
            timeout=timeout_sec,
            allow_redirects=True,
            stream=True,
            headers={**headers, "Range": "bytes=0-0"},
        )
        ok = resp.status_code in (200, 206)
        resp.close()
        return ok
    except Exception as exc:
        logger.warning("verify_public_object_url failed for %s: %s", u, exc)
        return False


def download_object_to_path(
    *,
    key: str | None = None,
    url: str | None = None,
    dest: Path,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    """Download an object via public CDN URL (preferred) or S3 GetObject."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    resolved_url = (url or "").strip() or (public_object_url(key) if key else None)
    if resolved_url:
        try:
            resp = requests.get(
                resolved_url,
                timeout=timeout_sec,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 MSTC-MediaFetch/1.0"},
            )
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return {
                "ok": True,
                "path": str(dest),
                "bytes": len(resp.content),
                "url": resolved_url,
            }
        except Exception as exc:
            logger.warning("CDN download failed %s: %s", resolved_url, exc)
            if not r2_configured() or not key:
                return {"ok": False, "error": str(exc), "url": resolved_url}

    if not key or not r2_configured():
        return {"ok": False, "error": "no url/key for download"}
    try:
        client = _s3_client()
        client.download_file(R2_BUCKET, key.lstrip("/"), str(dest))
        return {
            "ok": True,
            "path": str(dest),
            "bytes": dest.stat().st_size,
            "key": key.lstrip("/"),
        }
    except Exception as exc:
        logger.warning("S3 download failed key=%s: %s", key, exc)
        return {"ok": False, "error": str(exc), "key": key}


def upload_public_tree(
    public_dir: Path,
    *,
    relative_paths: list[str],
) -> dict[str, Any]:
    """Upload many relative public assets (pdfs/docs/thumbs) to R2."""
    ok_n = 0
    fail_n = 0
    errors: list[str] = []
    urls: list[str] = []
    for rel in relative_paths:
        key = str(rel).lstrip("/")
        local = Path(public_dir) / key
        if not local.is_file():
            fail_n += 1
            errors.append(f"missing:{key}")
            continue
        up = upload_file(local, key=key)
        if up.get("ok"):
            ok_n += 1
            if up.get("url"):
                urls.append(str(up["url"]))
        else:
            fail_n += 1
            errors.append(f"{key}:{up.get('error')}")
    return {"ok": fail_n == 0, "uploaded": ok_n, "failed": fail_n, "errors": errors, "urls": urls}


def stage_download_from_media(
    *,
    key: str | None,
    url: str | None,
    dest: Path,
) -> Path | None:
    """Ensure dest exists by downloading from CDN/R2 when missing."""
    dest = Path(dest)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    result = download_object_to_path(key=key, url=url, dest=dest)
    if result.get("ok") and dest.is_file():
        return dest
    return None


def temp_download_media(*, key: str | None = None, url: str | None = None) -> Path | None:
    suffix = Path(key or urlparse(url or "").path or "file.bin").suffix or ".bin"
    tmp = Path(tempfile.mkdtemp(prefix="mstc_media_")) / f"obj{suffix}"
    got = download_object_to_path(key=key, url=url, dest=tmp)
    if got.get("ok"):
        return tmp
    return None
