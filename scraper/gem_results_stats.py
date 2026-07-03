"""Scan all closed GeM Forward auctions and aggregate result statistics."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shlex
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from scraper.config import GEM_FORWARD_PER_PAGE, GEM_FORWARD_REQUEST_DELAY_SEC, REPO_ROOT, REQUEST_TIMEOUT, USER_AGENT
from scraper.emd import parse_emd_amount
from scraper.gem_forward_client import GemForwardClient, GemForwardTransportError
from scraper.gem_forward_parser import parse_listing_record_count

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
GEM_CLOSED_STATUS = "3"
TEN_LAKH = 1_000_000
BATCH_MARKER = "===GEM_BATCH_ID:"


def _batch_fetch_results_ssh(client: GemForwardClient, rows: list[dict[str, str]]) -> dict[str, str]:
    """Fetch multiple result pages in one SSH round-trip."""
    if not rows:
        return {}
    ssh = client._ensure_ssh()
    cookie = ssh._cookie_file
    parts: list[str] = []
    for row in rows:
        url = client._absolute_url(row["result_path"])
        marker = f"{BATCH_MARKER}{row['auction_id']}==="
        parts.append(
            f"printf '%s\\n' {shlex.quote(marker)}; "
            f"curl -sL -m {REQUEST_TIMEOUT} -A {shlex.quote(USER_AGENT)} "
            f"-b {shlex.quote(cookie)} -c {shlex.quote(cookie)} {shlex.quote(url)}; "
            f"printf '\\n'"
        )
    script = " ; ".join(parts)
    raw = ssh._remote(script)
    out: dict[str, str] = {}
    current_id = None
    buf: list[str] = []
    for line in raw.splitlines():
        if line.startswith(BATCH_MARKER) and line.endswith("==="):
            if current_id is not None:
                out[current_id] = "\n".join(buf)
            current_id = line[len(BATCH_MARKER) : -3]
            buf = []
        else:
            buf.append(line)
    if current_id is not None:
        out[current_id] = "\n".join(buf)
    return out


def parse_result_page(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for table in soup.select("table"):
        headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
        if not headers:
            continue
        lower = [h.lower() for h in headers]
        if not any("winning" in h or "bid price" in h or "bidder" in h for h in lower):
            continue
        for tr in table.select("tbody tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not cells or not any(c.strip() for c in cells):
                continue
            if len(cells) >= 6:
                items.append(
                    {
                        "sr_no": cells[0],
                        "item_name": cells[1],
                        "winning_bidder": cells[2] if len(cells) > 2 else None,
                        "winning_bid_inr": parse_emd_amount(cells[3]) if len(cells) > 3 else None,
                        "winning_bid_text": cells[3] if len(cells) > 3 else None,
                        "bid_datetime": cells[4] if len(cells) > 4 else None,
                        "acceptance_status": cells[5] if len(cells) > 5 else None,
                        "remarks": cells[6] if len(cells) > 6 else None,
                    }
                )
    return items


def parse_listing_result_paths(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, str]] = []
    for block in soup.select("div.eproc-listing-main"):
        index_label = block.select_one("div.index label")
        auction_id = None
        if index_label:
            match = re.search(r"Auction ID\s*:\s*(\d+)", index_label.get_text(" ", strip=True))
            auction_id = match.group(1) if match else None
        title_el = block.select_one("div.brief a")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        res = block.select_one('a[href*="auction-result"]')
        result_path = res["href"] if res and res.get("href") else ""
        if auction_id and result_path:
            rows.append({"auction_id": auction_id, "title": title, "result_path": result_path})
    return rows


def normalize_status(status: Optional[str]) -> str:
    if not status:
        return "unknown"
    s = status.strip().lower()
    if "accepted" in s and "pending" not in s and "rejected" not in s:
        return "accepted"
    if "rejected" in s:
        return "rejected"
    if "pending" in s:
        return "pending"
    return "other"


def summarize_auction(items: list[dict[str, Any]]) -> dict[str, Any]:
    bids = [i["winning_bid_inr"] for i in items if i.get("winning_bid_inr") is not None]
    statuses = [normalize_status(i.get("acceptance_status")) for i in items]
    total_bid = sum(bids) if bids else 0.0
    max_bid = max(bids) if bids else 0.0
    return {
        "lot_count": len(items),
        "total_bid_inr": total_bid,
        "max_lot_bid_inr": max_bid,
        "has_accepted": any(s == "accepted" for s in statuses),
        "all_accepted": bool(statuses) and all(s == "accepted" for s in statuses),
        "has_rejected": any(s == "rejected" for s in statuses),
        "has_pending": any(s == "pending" for s in statuses),
        "statuses": statuses,
    }


def scan_closed_results(
    *,
    transport: str = "ssh",
    delay: float = GEM_FORWARD_REQUEST_DELAY_SEC,
    category_id: str = "",
    max_pages: Optional[int] = None,
    checkpoint_path: Optional[Path] = None,
    on_auction: Optional[Any] = None,
) -> dict[str, Any]:
    client = GemForwardClient(transport=transport)
    client.init_session()

    processed_ids: set[str] = set()
    auctions_with_winners: list[dict[str, Any]] = []
    lot_status_counter: Counter[str] = Counter()
    stats = {
        "closed_total_listings": 0,
        "pages_scanned": 0,
        "result_pages_fetched": 0,
        "empty_result_tables": 0,
        "auctions_with_winners": 0,
        "total_lot_results": 0,
    }

    if checkpoint_path and checkpoint_path.exists():
        try:
            ck = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            processed_ids = set(ck.get("processed_ids", []))
            auctions_with_winners = ck.get("auctions_with_winners", [])
            lot_status_counter = Counter(ck.get("lot_status_counter", {}))
            stats.update(ck.get("stats", {}))
            logger.info("Resumed checkpoint: %d processed, %d winners", len(processed_ids), len(auctions_with_winners))
        except Exception as exc:
            logger.warning("Checkpoint load failed: %s", exc)

    html0 = client.search_auctions_html(page=1, per_page=GEM_FORWARD_PER_PAGE, status=GEM_CLOSED_STATUS, category_id=category_id)
    total_records = parse_listing_record_count(html0)
    total_pages = (total_records + GEM_FORWARD_PER_PAGE - 1) // GEM_FORWARD_PER_PAGE
    if max_pages:
        total_pages = min(total_pages, max_pages)

    for page in range(1, total_pages + 1):
        html = html0 if page == 1 else client.search_auctions_html(
            page=page, per_page=GEM_FORWARD_PER_PAGE, status=GEM_CLOSED_STATUS, category_id=category_id
        )
        listings = parse_listing_result_paths(html)
        pending_batch: list[dict[str, str]] = []
        stats["pages_scanned"] = page
        stats["closed_total_listings"] = total_records

        for row in listings:
            aid = row["auction_id"]
            if aid in processed_ids:
                continue
            pending_batch.append(row)

        # Batch-fetch result pages (one SSH round-trip per listing page)
        if pending_batch:
            time.sleep(delay)
            if client._active_transport == "ssh" or client._transport_mode == "ssh":
                html_by_id = _batch_fetch_results_ssh(client, pending_batch)
            else:
                html_by_id = {
                    row["auction_id"]: client.get_html(row["result_path"]) for row in pending_batch
                }

            for row in pending_batch:
                aid = row["auction_id"]
                result_html = html_by_id.get(aid, "")
                stats["result_pages_fetched"] += 1
                items = parse_result_page(result_html)
                processed_ids.add(aid)

                if not items:
                    stats["empty_result_tables"] += 1
                    continue

                summary = summarize_auction(items)
                for it in items:
                    lot_status_counter[normalize_status(it.get("acceptance_status"))] += 1

                record = {
                    "auction_id": aid,
                    "title": row["title"][:120],
                    "result_path": row["result_path"],
                    **summary,
                }
                auctions_with_winners.append(record)
                stats["auctions_with_winners"] = len(auctions_with_winners)
                stats["total_lot_results"] += len(items)

                if on_auction:
                    on_auction(record)

            pending_batch = []
            if checkpoint_path:
                _save_checkpoint(checkpoint_path, processed_ids, auctions_with_winners, lot_status_counter, stats)

        if page % 25 == 0:
            logger.info(
                "Page %d/%d | processed=%d winners=%d empty=%d",
                page, total_pages, len(processed_ids), len(auctions_with_winners), stats["empty_result_tables"],
            )

    if checkpoint_path:
        _save_checkpoint(checkpoint_path, processed_ids, auctions_with_winners, lot_status_counter, stats)

    return _build_report(auctions_with_winners, lot_status_counter, stats, total_records)


def _save_checkpoint(
    path: Path,
    processed_ids: set[str],
    winners: list[dict[str, Any]],
    lot_status_counter: Counter[str],
    stats: dict[str, Any],
) -> None:
    path.write_text(
        json.dumps(
            {
                "processed_ids": sorted(processed_ids),
                "auctions_with_winners": winners,
                "lot_status_counter": dict(lot_status_counter),
                "stats": stats,
            },
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )


def _build_report(
    auctions: list[dict[str, Any]],
    lot_status_counter: Counter[str],
    stats: dict[str, Any],
    total_closed: int,
) -> dict[str, Any]:
    n = len(auctions)
    any_accepted = sum(1 for a in auctions if a.get("has_accepted"))
    all_accepted = sum(1 for a in auctions if a.get("all_accepted"))
    total_ge_10l = sum(1 for a in auctions if (a.get("total_bid_inr") or 0) >= TEN_LAKH)
    max_ge_10l = sum(1 for a in auctions if (a.get("max_lot_bid_inr") or 0) >= TEN_LAKH)
    accepted_and_total_ge_10l = sum(
        1 for a in auctions if a.get("has_accepted") and (a.get("total_bid_inr") or 0) >= TEN_LAKH
    )
    accepted_and_all_ge_10l = sum(
        1 for a in auctions if a.get("all_accepted") and (a.get("total_bid_inr") or 0) >= TEN_LAKH
    )

    return {
        "generated_at": datetime.now(IST).isoformat(),
        "scope": "GeM Forward closed auctions (xStatus=3), all categories",
        "total_closed_listings": total_closed,
        "listings_processed": stats.get("result_pages_fetched", 0),
        "empty_result_tables": stats.get("empty_result_tables", 0),
        "auctions_with_winning_bids": n,
        "winner_rate_of_closed_pct": round(n / total_closed * 100, 2) if total_closed else 0,
        "total_lot_result_rows": sum(lot_status_counter.values()),
        "lot_status_breakdown": dict(lot_status_counter),
        "auction_level": {
            "any_lot_accepted": any_accepted,
            "all_lots_accepted": all_accepted,
            "total_bid_sum_ge_10_lakh": total_ge_10l,
            "max_lot_bid_ge_10_lakh": max_ge_10l,
            "any_accepted_and_total_bid_ge_10_lakh": accepted_and_total_ge_10l,
            "all_accepted_and_total_bid_ge_10_lakh": accepted_and_all_ge_10l,
        },
        "threshold_inr": TEN_LAKH,
        "stats": stats,
        "top_accepted_above_10l": sorted(
            [
                {
                    "auction_id": a["auction_id"],
                    "title": a.get("title"),
                    "total_bid_inr": a.get("total_bid_inr"),
                    "all_accepted": a.get("all_accepted"),
                }
                for a in auctions
                if a.get("has_accepted") and (a.get("total_bid_inr") or 0) >= TEN_LAKH
            ],
            key=lambda x: x["total_bid_inr"],
            reverse=True,
        )[:25],
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="GeM closed auction result statistics")
    parser.add_argument("--transport", default="ssh", choices=["auto", "direct", "ssh"])
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--category-id", default="", help="Optional catID filter (8=General Scrap)")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "work" / "gem_results_stats.json")
    parser.add_argument("--checkpoint", type=Path, default=REPO_ROOT / "work" / "gem_results_stats_checkpoint.json")
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ck = args.checkpoint if args.resume else None

    try:
        report = scan_closed_results(
            transport=args.transport,
            delay=args.delay,
            category_id=args.category_id,
            max_pages=args.max_pages,
            checkpoint_path=ck,
        )
    except GemForwardTransportError as exc:
        logger.error("Transport failed: %s", exc)
        if args.resume and args.checkpoint.exists():
            ck_data = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            report = _build_report(
                ck_data.get("auctions_with_winners", []),
                Counter(ck_data.get("lot_status_counter", {})),
                ck_data.get("stats", {}),
                ck_data.get("stats", {}).get("closed_total_listings", 0),
            )
            report["partial"] = True
            report["error"] = str(exc)
        else:
            return 1

    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("Wrote %s", args.out)
    print(json.dumps(report.get("auction_level", {}), indent=2))
    print(json.dumps(report.get("lot_status_breakdown", {}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
