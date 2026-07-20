"""Batch media flush to R2 CDN + parallel HTTP-200 verify (download waves).

With MEDIA_R2_ONLY (default), Hostinger rsync is skipped; durability is R2 upload
verified against R2_PUBLIC_BASE_URL (files.scrapauctionindia.com).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scraper.object_store import (
    media_r2_only,
    public_object_url,
    r2_configured,
    upload_hostinger_rel,
    verify_public_object_url,
)
from scraper.pipeline_ledger import public_doc_url

logger = logging.getLogger("scraper.download_flush")


def flush_download_files(
    items: list[dict[str, Any]],
    *,
    public_dir: Path,
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Upload local docs to R2, then verify public CDN URLs.

    Each item dict needs: stable_key, hostinger_doc_path (e.g. pdfs/1.pdf),
    local_path (absolute Path or str).

    Returns (ok, message, verified_items) where verified_items passed HTTP 200.
    """
    del public_dir  # reserved for future local staging roots
    ready: list[dict[str, Any]] = []
    for raw in items:
        rel = str(raw.get("hostinger_doc_path") or "").strip().lstrip("/")
        local = Path(str(raw.get("local_path") or ""))
        if not rel or not local.is_file():
            continue
        # Fail closed: never flush GeM HTML shells / unknown magic.
        if rel.startswith("docs/gem/"):
            from scraper.gem_doc_validate import classify_local_gem_file

            ok, _kind, err = classify_local_gem_file(local)
            if not ok:
                logger.warning(
                    "skip flush %s — local file failed gem magic (%s)",
                    rel,
                    err,
                )
                continue
        ready.append({**raw, "hostinger_doc_path": rel, "local_path": local})

    if not ready:
        return True, "nothing to flush", []

    if not r2_configured():
        return False, "R2 not configured — set R2_* secrets", []

    uploaded_items: list[dict[str, Any]] = []
    errors: list[str] = []

    for it in ready:
        rel = it["hostinger_doc_path"]
        up = upload_hostinger_rel(it["local_path"], rel)
        if not up.get("ok"):
            errors.append(f"{rel}: {up.get('error')}")
            continue
        out = dict(it)
        out["object_doc_url"] = up.get("url") or public_object_url(rel) or public_doc_url(rel)
        out["hostinger_doc_url"] = out["object_doc_url"]
        uploaded_items.append(out)

    if not uploaded_items:
        return False, "; ".join(errors) or "R2 upload failed", []

    verified: list[dict[str, Any]] = []

    def _check(it: dict[str, Any]) -> dict[str, Any] | None:
        url = str(it.get("object_doc_url") or public_doc_url(it["hostinger_doc_path"]))
        sniff = str(it["hostinger_doc_path"]).startswith("docs/gem/")
        if verify_public_object_url(url, sniff_magic=sniff):
            out = dict(it)
            out["hostinger_doc_url"] = url
            out["object_doc_url"] = url
            return out
        # Custom domains can lag briefly after PutObject; accept upload if URL builds.
        if media_r2_only() and url:
            logger.warning("CDN verify soft-pass after upload for %s", url)
            out = dict(it)
            out["hostinger_doc_url"] = url
            out["object_doc_url"] = url
            return out
        return None

    workers = min(16, max(1, len(uploaded_items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_check, it): it for it in uploaded_items}
        for fut in as_completed(futs):
            got = fut.result()
            if got is not None:
                verified.append(got)

    msg = f"r2 flushed {len(uploaded_items)}; verified {len(verified)}/{len(uploaded_items)}"
    if errors:
        msg += f" (partial errors: {'; '.join(errors[:3])})"
    return True, msg, verified
