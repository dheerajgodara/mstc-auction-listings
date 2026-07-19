"""Download GeM Forward tender documents into web/public/docs/{auction_id}/."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from scraper.config import DEFAULT_DOCS_DIR, GEM_FORWARD_REQUEST_DELAY_SEC
from scraper.document_cache import safe_lot_dirname
from scraper.gem_forward_client import GemForwardClient
from scraper.gem_scrap_samples_fetch import (
    _download_binary,
    _tender_doc_save_name,
    find_file_list_url,
    parse_file_list_html,
)
from scraper.models import AuctionRecord, LotDocument
from scraper.thumbnails import generate_thumbnail, get_pdf_page_count

logger = logging.getLogger(__name__)

MIN_DOC_BYTES = 500


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("._") or "document"


def attach_gem_documents(
    record: AuctionRecord,
    *,
    client: GemForwardClient,
    docs_dir: Path = DEFAULT_DOCS_DIR,
    thumbs_dir: Path | None = None,
    delay_sec: float = GEM_FORWARD_REQUEST_DELAY_SEC,
    max_docs: int = 20,
) -> AuctionRecord:
    """Fetch GeM file-list docs and attach to lot 1 (production path).

    GeM docs are NOT covered by MSTC ``process_auction_documents``. Without this,
    scrapauctionindia stores zero GeM annexures/PDFs.
    """
    if record.source != "gem_forward":
        return record
    aid = str(record.source_auction_id or "").strip()
    if not aid:
        return record

    notice_path = None
    if record.detail_url and "/eprocure/" in record.detail_url:
        notice_path = record.detail_url.split("/eprocure/", 1)[-1]
        notice_path = "/eprocure/" + notice_path
    if not notice_path:
        # Prefer stored document_urls notice-like paths
        for url in record.document_urls or []:
            if "view-auction-notice" in url:
                notice_path = "/eprocure/" + url.split("/eprocure/", 1)[-1]
                break
    if not notice_path:
        logger.info("GeM %s: no notice path; skip document download", aid)
        return record

    try:
        time.sleep(delay_sec)
        notice_html = client.get_html(notice_path)
    except Exception as exc:
        logger.warning("GeM %s: notice fetch failed: %s", aid, exc)
        return record

    file_list_path = find_file_list_url(notice_html, aid)
    if not file_list_path:
        logger.info("GeM %s: no file-list on notice", aid)
        return record

    try:
        time.sleep(delay_sec)
        file_list_html = client.get_html(file_list_path)
        docs_meta = parse_file_list_html(file_list_html)[:max_docs]
    except Exception as exc:
        logger.warning("GeM %s: file-list failed: %s", aid, exc)
        return record

    if not docs_meta:
        return record

    auction_docs = Path(docs_dir) / aid
    auction_docs.mkdir(parents=True, exist_ok=True)
    attached: list[LotDocument] = []
    preview: list[str] = []

    for doc in docs_meta:
        dl_path = doc.get("download_path") or ""
        if not dl_path:
            continue
        try:
            time.sleep(delay_sec)
            content = _download_binary(client, dl_path)
            if len(content) < MIN_DOC_BYTES:
                continue
            safe = _safe_name(_tender_doc_save_name(doc, content))
            dest = auction_docs / safe
            dest.write_bytes(content)
            mime = "application/pdf" if content[:4] == b"%PDF" else None
            page_count = get_pdf_page_count(dest) if mime == "application/pdf" else None
            cached_url = f"docs/{aid}/{safe}"
            thumb_url = None
            if thumbs_dir is not None and mime == "application/pdf":
                lot_key = safe_lot_dirname(
                    (record.lots[0].lot_id if record.lots else None) or "1"
                )
                lot_thumb_dir = Path(thumbs_dir) / aid / lot_key
                lot_thumb_dir.mkdir(parents=True, exist_ok=True)
                thumb_path = lot_thumb_dir / f"{Path(safe).stem}.webp"
                if generate_thumbnail(dest, thumb_path):
                    thumb_url = f"thumbs/{aid}/{lot_key}/{thumb_path.name}"
                    preview.append(thumb_url)
            attached.append(
                LotDocument(
                    type="annexure",
                    filename=safe,
                    status="thumbnail_ready" if thumb_url else "downloaded",
                    mime_type=mime,
                    page_count=page_count,
                    cached_url=cached_url,
                    thumbnail_url=thumb_url,
                    source_url=client._absolute_url(dl_path),
                )
            )
        except Exception as exc:
            logger.warning("GeM %s: doc download failed (%s): %s", aid, doc.get("filename"), exc)

    if not attached:
        return record

    lots = list(record.lots or [])
    if not lots:
        from scraper.models import LotRecord

        lots = [LotRecord(lot_id="1", item_title=record.item_summary or aid)]
    lot0 = lots[0].model_copy(deep=True)
    existing = list(lot0.documents or [])
    # Dedupe by filename
    have = {d.filename for d in existing if d.filename}
    for doc in attached:
        if doc.filename not in have:
            existing.append(doc)
    lot0.documents = existing
    if preview:
        lot0.preview_images = list(dict.fromkeys([*(lot0.preview_images or []), *preview]))
    lots[0] = lot0
    return record.model_copy(update={"lots": lots})
