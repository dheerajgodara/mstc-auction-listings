from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from scraper.config import SITE_BASE_URL


@dataclass
class HttpVerifyResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    index_status: int | None = None
    json_status: int | None = None
    data_js_status: int | None = None
    pdf_status: int | None = None
    thumb_status: int | None = None
    live_count_hint: int | None = None
    checked_urls: dict[str, str] = field(default_factory=dict)


def _http_status(url: str, *, timeout: int = 60) -> tuple[int, bytes]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "MSTC-Refresh-Verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read(500_000)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(500_000) if exc.fp else b""


def _pick_sample_urls(candidate_json: Path | None) -> tuple[str | None, str | None]:
    if not candidate_json or not candidate_json.is_file():
        return None, None
    data = json.loads(candidate_json.read_text(encoding="utf-8"))
    pdf_url = thumb_url = None
    for auction in data.get("auctions", []):
        if auction.get("source") != "mstc":
            continue
        if not pdf_url and auction.get("pdf_url"):
            pdf_url = auction["pdf_url"]
        for lot in auction.get("lots", []):
            for img in lot.get("preview_images") or []:
                url = img if isinstance(img, str) else (img.get("url") or img.get("thumbnail_url"))
                if url and not thumb_url:
                    thumb_url = url
                    break
            if thumb_url:
                break
        if pdf_url and thumb_url:
            break
    return pdf_url, thumb_url


def verify_live_site(
    *,
    base_url: str | None = None,
    expected_count: int | None = None,
    candidate_json: Path | None = None,
) -> HttpVerifyResult:
    errors: list[str] = []
    warnings: list[str] = []
    checked: dict[str, str] = {}

    site = (base_url or SITE_BASE_URL or "https://lightcyan-camel-979846.hostingersite.com/auctions").rstrip("/")
    index_url = f"{site}/"
    json_url = f"{site}/data/auctions.json"
    data_js_url = f"{site}/data/auctions-data.js"

    index_status, index_body = _http_status(index_url)
    checked["index"] = index_url
    if index_status != 200:
        errors.append(f"index returned HTTP {index_status}")

    json_status, _json_body = _http_status(json_url)
    checked["json"] = json_url
    if json_status == 403:
        warnings.append(
            "live JSON endpoint returned 403 (Hostinger may block .json; UI loads auctions-data.js client-side)"
        )
    elif json_status != 200:
        warnings.append(f"live JSON returned HTTP {json_status}")

    data_js_status, data_js_body = _http_status(data_js_url)
    checked["data_js"] = data_js_url
    if data_js_status != 200:
        warnings.append(f"live auctions-data.js returned HTTP {data_js_status}")
    elif b"__AUCTIONS_EXPORT__" not in data_js_body:
        warnings.append("live auctions-data.js missing __AUCTIONS_EXPORT__ global")

    live_count_hint = None
    if index_status == 200:
        html = index_body.decode("utf-8", errors="replace")
        if expected_count is not None and str(expected_count) in html:
            live_count_hint = expected_count
        elif data_js_status == 200:
            m = re.search(r'"count"\s*:\s*(\d+)', data_js_body.decode("utf-8", errors="replace"))
            if m:
                live_count_hint = int(m.group(1))
        if live_count_hint is None:
            m = re.search(r'"count"\s*:\s*(\d+)', html)
            if m:
                live_count_hint = int(m.group(1))
            elif expected_count is not None:
                warnings.append(f"could not confirm expected count {expected_count} on live site")

    pdf_rel, thumb_rel = _pick_sample_urls(candidate_json)
    pdf_status = thumb_status = None
    if pdf_rel:
        pdf_url = f"{site}/{pdf_rel.lstrip('/')}"
        pdf_status, _ = _http_status(pdf_url)
        checked["pdf"] = pdf_url
        if pdf_status != 200:
            errors.append(f"sample PDF returned HTTP {pdf_status}: {pdf_url}")
    else:
        warnings.append("no sample PDF URL available for HTTP check")

    if thumb_rel:
        thumb_url = f"{site}/{thumb_rel.lstrip('/')}"
        thumb_status, _ = _http_status(thumb_url)
        checked["thumb"] = thumb_url
        if thumb_status != 200:
            warnings.append(f"sample thumbnail returned HTTP {thumb_status}: {thumb_url}")

    return HttpVerifyResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        index_status=index_status,
        json_status=json_status,
        data_js_status=data_js_status,
        pdf_status=pdf_status,
        thumb_status=thumb_status,
        live_count_hint=live_count_hint,
        checked_urls=checked,
    )
