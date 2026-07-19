"""Download full details for Accepted + >=10L GeM Forward auctions."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from scraper.config import GEM_FORWARD_REQUEST_DELAY_SEC, GEM_FORWARD_STATUS_CLOSED, REPO_ROOT
from scraper.emd import format_inr_amount, format_inr_or_dash
from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError
from scraper.gem_forward_parser import parse_detail_page, parse_rules_page
from scraper.gem_results_stats import TEN_LAKH, summarize_auction
from scraper.gem_scrap_samples_fetch import (
    enrich_auction,
    parse_listing_block,
    parse_result_page,
)

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
GEM_CLOSED = GEM_FORWARD_STATUS_CLOSED


def load_premium_from_checkpoint(path: Path) -> list[dict[str, Any]]:
    ck = json.loads(path.read_text(encoding="utf-8"))
    winners = ck.get("auctions_with_winners", [])
    return [
        a
        for a in winners
        if a.get("has_accepted") and (a.get("total_bid_inr") or 0) >= TEN_LAKH
    ]


def notice_path_from_result_html(html: str, auction_id: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select('a[href*="view-auction-notice"]'):
        href = a.get("href", "")
        if auction_id in href:
            return href
    match = re.search(
        rf'/eprocure/view-auction-notice/{auction_id}/[^"\'>\s]+',
        html,
        re.I,
    )
    return match.group(0) if match else None


def find_listing_paths(client: GemForwardClient, auction_id: str, delay: float) -> dict[str, str]:
    """Locate notice/result paths via closed search."""
    time.sleep(delay)
    html = client.search_auctions_html(page=1, per_page=10, status=GEM_CLOSED, keyword=auction_id)
    soup = BeautifulSoup(html, "lxml")
    for block in soup.select("div.eproc-listing-main"):
        listing = parse_listing_block(block)
        if listing.get("auction_id") == auction_id:
            res = block.select_one('a[href*="auction-result"]')
            return {
                "notice_path": listing.get("notice_path") or "",
                "result_path": res["href"] if res and res.get("href") else "",
                "title": listing.get("title") or "",
            }
    return {}


def fetch_premium_auctions(
    summaries: list[dict[str, Any]],
    *,
    transport: str = "ssh",
    delay: float = GEM_FORWARD_REQUEST_DELAY_SEC,
    docs_dir: Path,
    checkpoint_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    client = GemForwardClient(transport=transport)
    client.init_session()

    done_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    if checkpoint_path and checkpoint_path.exists():
        try:
            ck = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            records = ck.get("auctions", [])
            done_ids = {r["auction_id"] for r in records}
            logger.info("Resume: %d already fetched", len(done_ids))
        except Exception as exc:
            logger.warning("Checkpoint load failed: %s", exc)

    for i, summary in enumerate(summaries, 1):
        aid = summary["auction_id"]
        if aid in done_ids:
            continue
        logger.info("[%d/%d] Enriching auction %s", i, len(summaries), aid)

        result_path = summary.get("result_path") or ""
        notice_path = ""
        title = summary.get("title") or ""

        if result_path:
            time.sleep(delay)
            result_html = client.get_html(result_path)
            notice_path = notice_path_from_result_html(result_html, aid) or ""
        else:
            result_html = ""

        if not notice_path:
            paths = find_listing_paths(client, aid, delay)
            notice_path = paths.get("notice_path") or ""
            result_path = result_path or paths.get("result_path") or ""
            title = title or paths.get("title") or ""
            if result_path and not result_html:
                time.sleep(delay)
                result_html = client.get_html(result_path)

        listing = {
            "auction_id": aid,
            "title": title,
            "notice_path": notice_path,
            "result_path": result_path,
            "organisation": [],
        }

        record = enrich_auction(client, listing, docs_dir=docs_dir, delay=delay)

        if result_html and not record.get("result_items"):
            record["result_items"] = parse_result_page(result_html)
        elif result_path and not record.get("result_items"):
            time.sleep(delay)
            record["result_items"] = parse_result_page(client.get_html(result_path))

        fresh = summarize_auction(record.get("result_items") or [])
        record["checkpoint_summary"] = summary
        record["fresh_summary"] = fresh
        record["fetched_at"] = datetime.now(IST).isoformat()

        records.append(record)
        done_ids.add(aid)

        if checkpoint_path:
            checkpoint_path.write_text(
                json.dumps(
                    {"auctions": records, "count": len(records)},
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )

    return records


def generate_report(records: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines = [
        "# GeM Forward — Accepted + ≥ ₹10 Lakh (Full Detail Archive)",
        "",
        f"**Generated:** {meta.get('generated_at')}",
        f"**Auctions:** {len(records)}",
        f"**Criteria:** At least one lot **Accepted** AND total H1 bid ≥ **₹10,00,000**",
        "",
        "## Summary Table",
        "",
        "| # | ID | Title | Total H1 ₹ | Lots | Accepted | Docs | PDF lines |",
        "|---|-----|-------|------------|------|----------|------|-----------|",
    ]
    for i, r in enumerate(sorted(records, key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or x.get("checkpoint_summary", {}).get("total_bid_inr") or 0)), 1):
        fs = r.get("fresh_summary") or r.get("checkpoint_summary") or {}
        total = fs.get("total_bid_inr", 0)
        lines.append(
            f"| {i} | {r.get('auction_id')} | {(r.get('title') or '')[:45]} | "
            f"{format_inr_amount(total)} | {fs.get('lot_count', len(r.get('result_items') or []))} | "
            f"{'Yes' if fs.get('has_accepted') or r.get('checkpoint_summary', {}).get('has_accepted') else 'No'} | "
            f"{len(r.get('documents') or [])} | {len(r.get('lot_lines') or [])} |"
        )

    lines.extend(["", "---", ""])
    for i, r in enumerate(sorted(records, key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or 0)), 1):
        lines.extend(_auction_section(r, i))

    lines.extend([
        "",
        "## Methodology",
        "",
        "- Source: GeM Forward closed auctions checkpoint filter",
        "- Fetched: result page, notice, business rules, file-list attachments, PDF text",
        "- Data: `work/gem_premium_auctions.json` + `work/gem_premium_docs/{id}/`",
        "",
    ])
    return "\n".join(lines)


def _auction_section(r: dict[str, Any], index: int) -> list[str]:
    fs = r.get("fresh_summary") or {}
    ck = r.get("checkpoint_summary") or {}
    total = fs.get("total_bid_inr") or ck.get("total_bid_inr")
    lines = [
        f"## {index}. Auction {r.get('auction_id')} — {r.get('title', '')[:100]}",
        "",
        f"**Total H1:** {format_inr_amount(total, decimals=2)}" if total else "",
        f"**Seller:** {r.get('seller_name') or '—'}",
        f"**Category:** {r.get('category') or '—'}",
        "",
    ]
    if r.get("auction_brief"):
        lines.extend(["### Brief", "", r["auction_brief"], ""])
    if r.get("auction_detail"):
        lines.extend(["### Detail", "", r["auction_detail"][:8000], ""])
    if r.get("opening_items"):
        lines.extend(["### Opening prices (rules)", "", "| Sr | Item | Opening ₹ | Increment ₹ |", "|----|------|-----------|-------------|"])
        for oi in r["opening_items"]:
            op = oi.get("opening_price_inr")
            inc = oi.get("increment_price_inr")
            lines.append(
                f"| {oi.get('sr_no')} | {(oi.get('item_name') or '')[:50]} | "
                f"{format_inr_or_dash(op)} | {format_inr_or_dash(inc)} |"
            )
        lines.append("")
    if r.get("result_items"):
        lines.extend(["### Winning bids (results)", "", "| Sr | Item | Bidder | H1 ₹ | Time | Status |", "|----|------|--------|------|------|--------|"])
        for ri in r["result_items"]:
            bid = ri.get("winning_bid_inr")
            lines.append(
                f"| {ri.get('sr_no')} | {(ri.get('item_name') or '')[:40]} | {ri.get('winning_bidder') or '—'} | "
                f"{format_inr_amount(bid, decimals=2) if bid else ri.get('winning_bid_text', '—')} | {ri.get('bid_datetime') or '—'} | "
                f"{ri.get('acceptance_status') or '—'} |"
            )
        lines.append("")
    if r.get("lot_lines"):
        lines.extend(["### Lot lines (from PDFs)", ""])
        for ll in r["lot_lines"][:40]:
            lines.append(f"- {ll.get('raw_line', '')[:120]}")
        lines.append("")
    if r.get("documents"):
        lines.extend(["### Documents", ""])
        for d in r["documents"]:
            lines.append(f"- **{d.get('description') or d.get('filename')}** → `{d.get('local_path', '—')}` ({d.get('text_length', 0)} chars)")
        lines.append("")
    if r.get("extraction_warnings"):
        lines.extend(["### Warnings", ""] + [f"- {w}" for w in r["extraction_warnings"]] + [""])
    urls = []
    if r.get("result_path"):
        urls.append(f"Result: https://forwardauction.gem.gov.in{r['result_path']}")
    if r.get("notice_path"):
        urls.append(f"Notice: https://forwardauction.gem.gov.in{r['notice_path']}")
    if urls:
        lines.extend(urls + ["", "---", ""])
    return [ln for ln in lines if ln is not None]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Fetch premium GeM auction details")
    parser.add_argument("--checkpoint-in", type=Path, default=REPO_ROOT / "work" / "gem_results_stats_checkpoint.json")
    parser.add_argument("--json-out", type=Path, default=REPO_ROOT / "work" / "gem_premium_auctions.json")
    parser.add_argument("--md-out", type=Path, default=REPO_ROOT / "work" / "gem_premium_auctions_report.md")
    parser.add_argument("--fetch-checkpoint", type=Path, default=REPO_ROOT / "work" / "gem_premium_fetch_checkpoint.json")
    parser.add_argument("--docs-dir", type=Path, default=REPO_ROOT / "work" / "gem_premium_docs")
    parser.add_argument("--transport", default="ssh")
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    summaries = load_premium_from_checkpoint(args.checkpoint_in)
    logger.info("Premium auctions to fetch: %d", len(summaries))

    args.docs_dir.mkdir(parents=True, exist_ok=True)
    ck_path = args.fetch_checkpoint if args.resume else None
    if not args.resume and args.fetch_checkpoint.exists():
        args.fetch_checkpoint.unlink(missing_ok=True)

    try:
        records = fetch_premium_auctions(
            summaries,
            transport=args.transport,
            delay=args.delay,
            docs_dir=args.docs_dir,
            checkpoint_path=ck_path,
        )
    except GemForwardTransportError as exc:
        logger.error("Failed: %s", exc)
        if args.fetch_checkpoint.exists():
            records = json.loads(args.fetch_checkpoint.read_text()).get("auctions", [])
        else:
            return 1

    meta = {"generated_at": datetime.now(IST).isoformat(), "count": len(records), "criteria": "accepted_and_ge_10lakh"}
    payload = {"meta": meta, "auctions": records}
    args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    args.md_out.write_text(generate_report(records, meta), encoding="utf-8")
    logger.info("Wrote %s and %s", args.json_out, args.md_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
