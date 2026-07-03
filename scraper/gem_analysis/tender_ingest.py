"""Fetch tender PDFs and run OCR for GeM premium auctions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scraper.config import REPO_ROOT
from scraper.gem_forward_client import GemForwardClient
from scraper.gem_scrap_samples_fetch import _download_binary, find_file_list_url, parse_file_list_html

DOCS_DIR = REPO_ROOT / "work" / "gem_premium_docs"


def _file_list_paths(notice_html: str) -> list[str]:
    paths = set()
    for m in re.findall(r"/eprocure/xcommon/ajax/file-list/[^\"']+", notice_html):
        paths.add(m)
    for m in re.findall(r"file-list/[^\"']+", notice_html):
        paths.add("/eprocure/xcommon/ajax/" + m)
    return list(paths)


def ingest_auction(auction_id: str, notice_path: str, *, transport: str = "ssh") -> Path:
    out = DOCS_DIR / auction_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)

    client = GemForwardClient(transport=transport)
    client.init_session()
    notice = client.get_html(notice_path)

    manifest: dict[str, Any] = {"auction_id": auction_id, "pdfs": [], "pages": []}

    file_lists = _file_list_paths(notice)
    fl_primary = find_file_list_url(notice, auction_id)
    if fl_primary and fl_primary not in file_lists:
        file_lists.insert(0, fl_primary)

    for fl in file_lists:
        try:
            html = client.get_html(fl)
            for doc in parse_file_list_html(html):
                b = _download_binary(client, doc["download_path"])
                desc = doc.get("description") or "document"
                safe = re.sub(r"[^\w.\-]+", "_", desc).strip("_") + ".pdf"
                fp = out / safe
                if fp.is_file() and fp.stat().st_size == len(b):
                    continue
                fp.write_bytes(b)
                manifest["pdfs"].append({"file": safe, "description": desc, "bytes": len(b)})
        except Exception:
            continue

    from scraper.gem_analysis.asset_render import render_all_pdf_pages

    pages = render_all_pdf_pages(auction_id)
    manifest["pages"] = pages

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
