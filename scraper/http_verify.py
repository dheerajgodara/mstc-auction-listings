from __future__ import annotations

import http.client
import json
import re
import ssl
import urllib.error
import urllib.parse
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


def _encode_url_path(url: str) -> str:
    """Percent-encode path segments that contain spaces / unsafe chars."""
    parts = urllib.parse.urlsplit(url)
    encoded_path = "/".join(
        urllib.parse.quote(seg, safe=":@-._~!$&'()*+,;=") if seg else seg
        for seg in parts.path.split("/")
    )
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, encoded_path, parts.query, parts.fragment)
    )


def _url_has_unsafe_chars(url: str) -> bool:
    return any(ch.isspace() or ord(ch) < 32 for ch in url)


def _http_status(url: str, *, timeout: int = 60) -> tuple[int | None, bytes, str | None]:
    """Return (status, body, error_note). status is None when URL is invalid after encode."""
    ctx = ssl.create_default_context()
    candidates = [url]
    if _url_has_unsafe_chars(url):
        candidates.append(_encode_url_path(url))
    last_note: str | None = None
    for candidate in candidates:
        req = urllib.request.Request(candidate, headers={"User-Agent": "MSTC-Refresh-Verify/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.status, resp.read(500_000), None
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(500_000) if exc.fp else b"", None
        except (http.client.InvalidURL, UnicodeError, ValueError) as exc:
            last_note = f"invalid URL: {exc}"
            continue
        except urllib.error.URLError as exc:
            last_note = f"URL error: {exc}"
            continue
    return None, b"", last_note


def _asset_exists(output_assets_dir: Path | None, rel_url: str) -> bool:
    raw = str(rel_url or "").strip()
    if raw.startswith(("http://", "https://")):
        from scraper.config import R2_PUBLIC_BASE_URL

        base = (R2_PUBLIC_BASE_URL or "").rstrip("/")
        if base and raw.startswith(base + "/"):
            return True
        if "files.csmg.in/" in raw or "files.scrapauctionindia.com/" in raw or ".r2.dev/" in raw:
            return True
        # Non-CDN absolute URLs are not local build assets.
        return False
    if output_assets_dir is None:
        return True
    rel = raw.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    return (output_assets_dir / rel).is_file()


def _pick_sample_urls(
    candidate_json: Path | None,
    *,
    output_assets_dir: Path | None = None,
) -> tuple[str | None, str | None, list[str]]:
    if not candidate_json or not candidate_json.is_file():
        return None, None, []
    data = json.loads(candidate_json.read_text(encoding="utf-8"))
    skipped_missing_assets: list[str] = []
    pdf_candidates: list[str] = []
    thumb_candidates: list[str] = []
    for auction in data.get("auctions", []):
        if auction.get("source") != "mstc":
            continue
        if auction.get("pdf_url"):
            candidate_pdf = str(auction["pdf_url"])
            if _asset_exists(output_assets_dir, candidate_pdf):
                pdf_candidates.append(candidate_pdf)
            else:
                skipped_missing_assets.append(candidate_pdf)
        for lot in auction.get("lots", []):
            for img in lot.get("preview_images") or []:
                url = img if isinstance(img, str) else (img.get("url") or img.get("thumbnail_url"))
                if not url:
                    continue
                url_s = str(url)
                if _asset_exists(output_assets_dir, url_s):
                    thumb_candidates.append(url_s)
                else:
                    skipped_missing_assets.append(url_s)
            for doc in lot.get("documents") or []:
                if not isinstance(doc, dict):
                    continue
                if doc.get("status") != "thumbnail_ready":
                    continue
                thumb = doc.get("thumbnail_url")
                if thumb:
                    url_s = str(thumb)
                    if _asset_exists(output_assets_dir, url_s):
                        thumb_candidates.append(url_s)
                    else:
                        skipped_missing_assets.append(url_s)
                cached = doc.get("cached_url")
                if cached:
                    url_s = str(cached)
                    is_media = url_s.startswith(("docs/", "pdfs/")) or (
                        url_s.startswith("http")
                        and (
                            "files.scrapauctionindia.com/" in url_s
                            or "files.csmg.in/" in url_s
                            or ".r2.dev/" in url_s
                            or "/docs/" in url_s
                            or "/pdfs/" in url_s
                        )
                    )
                    if is_media:
                        if _asset_exists(output_assets_dir, url_s):
                            pdf_candidates.append(url_s)
                        else:
                            skipped_missing_assets.append(url_s)

    def _prefer_clean(urls: list[str]) -> str | None:
        if not urls:
            return None
        clean = [u for u in urls if not _url_has_unsafe_chars(u)]
        return (clean or urls)[0]

    return _prefer_clean(pdf_candidates), _prefer_clean(thumb_candidates), skipped_missing_assets[:10]


def verify_live_site(
    *,
    base_url: str | None = None,
    expected_count: int | None = None,
    candidate_json: Path | None = None,
    output_assets_dir: Path | None = None,
) -> HttpVerifyResult:
    errors: list[str] = []
    warnings: list[str] = []
    checked: dict[str, str] = {}

    site = (base_url or SITE_BASE_URL or "https://scrapauctionindia.com/auctions").rstrip("/")
    index_url = f"{site}/"
    json_url = f"{site}/data/auctions.json"
    data_js_url = f"{site}/data/auctions-data.js"

    index_status, index_body, index_note = _http_status(index_url)
    checked["index"] = index_url
    if index_status is None:
        errors.append(f"index URL invalid: {index_note}")
    elif index_status != 200:
        errors.append(f"index returned HTTP {index_status}")

    json_status, _json_body, json_note = _http_status(json_url)
    checked["json"] = json_url
    if json_status is None:
        warnings.append(f"live JSON URL invalid: {json_note}")
    elif json_status == 403:
        warnings.append(
            "live JSON endpoint returned 403 (Hostinger may block .json; UI loads auctions-data.js client-side)"
        )
    elif json_status != 200:
        warnings.append(f"live JSON returned HTTP {json_status}")

    data_js_status, data_js_body, data_js_note = _http_status(data_js_url)
    checked["data_js"] = data_js_url
    if data_js_status is None:
        warnings.append(f"live auctions-data.js URL invalid: {data_js_note}")
    elif data_js_status != 200:
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

    pdf_rel, thumb_rel, skipped_missing_assets = _pick_sample_urls(
        candidate_json,
        output_assets_dir=output_assets_dir,
    )
    if skipped_missing_assets:
        warnings.append(
            "skipped HTTP sample assets missing from build output: "
            + ", ".join(skipped_missing_assets)
        )
    pdf_status = thumb_status = None
    if pdf_rel:
        if str(pdf_rel).startswith("http://") or str(pdf_rel).startswith("https://"):
            pdf_url = str(pdf_rel)
        else:
            pdf_url = f"{site}/{pdf_rel.lstrip('/')}"
        pdf_status, _, pdf_note = _http_status(pdf_url)
        checked["pdf"] = pdf_url
        if pdf_status is None:
            warnings.append(f"sample PDF URL skipped (invalid): {pdf_note or pdf_url}")
        elif pdf_status != 200:
            errors.append(f"sample PDF returned HTTP {pdf_status}: {pdf_url}")
    else:
        warnings.append("no sample PDF URL available for HTTP check")

    if thumb_rel:
        if str(thumb_rel).startswith("http://") or str(thumb_rel).startswith("https://"):
            thumb_url = str(thumb_rel)
        else:
            thumb_url = f"{site}/{thumb_rel.lstrip('/')}"
        thumb_status, _, thumb_note = _http_status(thumb_url)
        checked["thumb"] = thumb_url
        if thumb_status is None:
            warnings.append(f"sample thumbnail URL skipped (invalid): {thumb_note or thumb_url}")
        elif thumb_status != 200:
            # Lot document thumbs are first-class media; treat 404 as deploy failure.
            errors.append(f"sample thumbnail returned HTTP {thumb_status}: {thumb_url}")

    sitemap_url = f"{site}/sitemap.xml"
    sitemap_status, sitemap_body, sitemap_note = _http_status(sitemap_url)
    checked["sitemap"] = sitemap_url
    if sitemap_status is None:
        errors.append(f"sitemap URL invalid: {sitemap_note}")
    elif sitemap_status != 200:
        errors.append(f"sitemap returned HTTP {sitemap_status}")
    else:
        sitemap_text = sitemap_body.decode("utf-8", errors="replace")
        if "<urlset" not in sitemap_text:
            errors.append("sitemap missing urlset root element")
        if "?q=" in sitemap_text or "?source=" in sitemap_text:
            errors.append("sitemap contains query-string URLs")

    detail_candidates: list[str] = []
    if candidate_json and candidate_json.is_file():
        try:
            export = json.loads(candidate_json.read_text(encoding="utf-8"))
            for auction in export.get("auctions", []):
                source = str(auction.get("source") or "mstc").strip().lower()
                aid = str(auction.get("source_auction_id") or auction.get("id") or "").strip()
                if ":" in aid:
                    aid = aid.split(":", 1)[-1]
                slug = {"gem_forward": "gem-forward", "eauction": "eauction"}.get(source, "mstc")
                if aid and re.fullmatch(r"[A-Za-z0-9._-]+", aid):
                    detail_candidates.append(f"{slug}/{aid}")
                if len(detail_candidates) >= 8:
                    break
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    for fallback in ("mstc/588051", "mstc/582972", "mstc/584985"):
        if fallback not in detail_candidates:
            detail_candidates.append(fallback)

    detail_checked = False
    for rel in detail_candidates:
        detail_url = f"{site}/{rel}/"
        detail_status, detail_body, detail_note = _http_status(detail_url)
        checked["detail_sample"] = detail_url
        if detail_status is None:
            warnings.append(f"sample detail URL skipped (invalid): {detail_note or detail_url}")
            continue
        if detail_status == 404:
            continue
        detail_checked = True
        if detail_status != 200:
            warnings.append(f"sample detail page returned HTTP {detail_status}: {detail_url}")
        elif b"<h1" not in detail_body:
            warnings.append("sample detail page missing H1")
        break
    if not detail_checked:
        warnings.append(
            "sample detail page aged out for all candidates: "
            + ", ".join(detail_candidates[:5])
        )

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
