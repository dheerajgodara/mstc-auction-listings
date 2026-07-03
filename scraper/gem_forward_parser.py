from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from scraper.emd import parse_emd_amount

IST = ZoneInfo("Asia/Kolkata")

_AUCTION_ID_RE = re.compile(r"Auction ID\s*:\s*(\d+)", re.I)
_DATE_PAIR_RE = re.compile(
    r"Start Date\s*:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}).*?"
    r"End Date\s*:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})",
    re.I | re.S,
)
_RECORD_COUNT_RE = re.compile(r'id="recordCount"[^>]*value="(\d+)"', re.I)
_NOTICE_PATH_RE = re.compile(r"/eprocure/view-auction-notice/(\d+)/\d+/([A-F0-9]+)", re.I)
_DOC_PATH_RE = re.compile(r"/eprocure/eauction-download-document/(\d+)/([A-F0-9]+)", re.I)
_RULES_PATH_RE = re.compile(r"/eprocure/view-configure-rule/(\d+)/[^\"]+", re.I)


class GemForwardItem(BaseModel):
    sr_no: int
    item_name: str
    opening_price_inr: Optional[float] = None
    increment_price_inr: Optional[float] = None
    extension_increment_inr: Optional[float] = None


class GemForwardListing(BaseModel):
    auction_id: str
    title: str
    notice_path: str
    notice_token: str
    document_path: Optional[str] = None
    document_token: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    opening: Optional[datetime] = None
    closing: Optional[datetime] = None
    organisation: list[str] = Field(default_factory=list)


class GemForwardAuction(GemForwardListing):
    source: str = "gem_forward"
    category: Optional[str] = None
    sub_category: Optional[str] = None
    auction_brief: Optional[str] = None
    auction_detail: Optional[str] = None
    seller_name: Optional[str] = None
    emd_required: Optional[bool] = None
    emd_amount_inr: Optional[float] = None
    rules_path: Optional[str] = None
    items: list[GemForwardItem] = Field(default_factory=list)
    min_opening_price_inr: Optional[float] = None
    detail_url: Optional[str] = None
    document_url: Optional[str] = None
    rules_url: Optional[str] = None


def parse_gem_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value.strip())
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def parse_inr_text(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    return parse_emd_amount(value)


def parse_listing_record_count(html: str) -> int:
    match = _RECORD_COUNT_RE.search(html)
    return int(match.group(1)) if match else 0


def _label_value_pairs(soup: BeautifulSoup) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for group in soup.select("div.form-group"):
        caption = group.select_one("label.caption")
        if not caption:
            continue
        key = caption.get_text(" ", strip=True).rstrip(" :").strip()
        value_label = None
        for lbl in group.select("label.control-label"):
            if lbl is caption:
                continue
            if "caption" not in (lbl.get("class") or []):
                value_label = lbl
                break
        if value_label is None:
            value_div = group.select_one("div.col-sm-6 label.control-label, div.col-sm-9 label.control-label")
            value_label = value_div
        if key and value_label:
            pairs[key] = value_label.get_text(" ", strip=True)
    return pairs


def parse_listing_page(html: str, *, base_url: str = "https://forwardauction.gem.gov.in") -> list[GemForwardListing]:
    soup = BeautifulSoup(html, "lxml")
    listings: list[GemForwardListing] = []

    for block in soup.select("div.eproc-listing-main"):
        content = block.select_one("div.listing-content")
        if not content:
            continue

        index_label = content.select_one("div.index label")
        auction_id = None
        if index_label:
            match = _AUCTION_ID_RE.search(index_label.get_text(" ", strip=True))
            auction_id = match.group(1) if match else None

        title_link = content.select_one("div.brief a")
        title = title_link.get_text(" ", strip=True) if title_link else ""
        notice_path = ""
        notice_token = ""
        if title_link and title_link.get("href"):
            notice_path = title_link["href"]
            path_match = _NOTICE_PATH_RE.search(notice_path)
            if path_match:
                auction_id = auction_id or path_match.group(1)
                notice_token = path_match.group(2)

        date_text = content.select_one("div.listing-date-info span.blink")
        opening = closing = None
        if date_text:
            pair = _DATE_PAIR_RE.search(date_text.get_text(" ", strip=True))
            if pair:
                opening = parse_gem_datetime(pair.group(1))
                closing = parse_gem_datetime(pair.group(2))

        location_wrapper = content.select_one("div.date-icon.wid-27")
        if location_wrapper and location_wrapper.parent:
            loc_parts = [
                s.get_text(strip=True)
                for s in location_wrapper.parent.select("span")
                if s.get_text(strip=True) and s.get_text(strip=True) not in {"-", "...", "View More"}
            ]
        else:
            loc_parts = []
        city = district = state = pincode = None
        if loc_parts:
            city = loc_parts[0]
            if len(loc_parts) > 1:
                district = loc_parts[1]
            if len(loc_parts) > 2:
                state = loc_parts[2]
            if loc_parts and loc_parts[-1].isdigit() and len(loc_parts[-1]) == 6:
                pincode = loc_parts[-1]

        orgs: list[str] = []
        for dept in content.select("span.x-dept-name"):
            text = dept.get_text(" ", strip=True)
            if text:
                orgs.append(text.lstrip("\uf0f7 ").strip())

        document_path = document_token = None
        doc_link = block.select_one('a[href*="eauction-download-document"]')
        if doc_link and doc_link.get("href"):
            document_path = doc_link["href"]
            doc_match = _DOC_PATH_RE.search(document_path)
            if doc_match:
                document_token = doc_match.group(2)

        if not auction_id:
            continue

        listings.append(
            GemForwardListing(
                auction_id=auction_id,
                title=title,
                notice_path=notice_path,
                notice_token=notice_token,
                document_path=document_path,
                document_token=document_token,
                city=city,
                district=district,
                state=state,
                pincode=pincode,
                opening=opening,
                closing=closing,
                organisation=orgs,
            )
        )

    return listings


def parse_detail_page(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    pairs = _label_value_pairs(soup)

    allow_emd_el = soup.find("input", id="allowEmd")
    emd_required = None
    if allow_emd_el and allow_emd_el.get("value") is not None:
        emd_required = allow_emd_el["value"] == "1"

    rules_link = soup.select_one('a[href*="view-configure-rule"]')
    rules_path = rules_link["href"] if rules_link and rules_link.get("href") else None

    location_rows = []
    for tr in soup.select("#projectLocationTable tbody tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 5:
            location_rows.append(
                {
                    "pincode": cells[1],
                    "city": cells[2],
                    "district": cells[3],
                    "state": cells[4],
                }
            )

    return {
        "category": pairs.get("Category"),
        "auction_brief": pairs.get("Auction Brief"),
        "auction_detail": pairs.get("Auction Detail"),
        "seller_name": pairs.get("Seller/Auctioneer Name"),
        "opening_text": pairs.get("Auction Start Date & Time"),
        "closing_text": pairs.get("Auction End Date & Time"),
        "emd_required": emd_required,
        "rules_path": rules_path,
        "location_rows": location_rows,
        "label_pairs": pairs,
    }


def parse_rules_page(html: str) -> list[GemForwardItem]:
    soup = BeautifulSoup(html, "lxml")
    items: list[GemForwardItem] = []

    for table in soup.select("table.clear-table-details"):
        headers = [th.get_text(" ", strip=True).lower() for th in table.select("thead th")]
        if not any("opening price" in h for h in headers):
            continue
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            sr_text = cells[0].get_text(strip=True)
            try:
                sr_no = int(sr_text)
            except ValueError:
                continue
            item_name = cells[1].get_text(" ", strip=True)
            opening = parse_inr_text(cells[2].get_text(strip=True)) if len(cells) > 2 else None
            increment = parse_inr_text(cells[3].get_text(strip=True)) if len(cells) > 3 else None
            ext_increment = parse_inr_text(cells[4].get_text(strip=True)) if len(cells) > 4 else None
            items.append(
                GemForwardItem(
                    sr_no=sr_no,
                    item_name=item_name,
                    opening_price_inr=opening,
                    increment_price_inr=increment,
                    extension_increment_inr=ext_increment,
                )
            )
    return items


def merge_auction(
    listing: GemForwardListing,
    detail: dict[str, Any],
    items: list[GemForwardItem],
    *,
    base_url: str = "https://forwardauction.gem.gov.in",
) -> GemForwardAuction:
    opening = listing.opening or parse_gem_datetime(detail.get("opening_text"))
    closing = listing.closing or parse_gem_datetime(detail.get("closing_text"))

    loc = (detail.get("location_rows") or [None])[0] or {}
    city = listing.city or loc.get("city")
    district = listing.district or loc.get("district")
    state = listing.state or loc.get("state")
    pincode = listing.pincode or loc.get("pincode")

    prices = [i.opening_price_inr for i in items if i.opening_price_inr is not None]
    rules_path = detail.get("rules_path")
    notice_url = f"{base_url}{listing.notice_path}" if listing.notice_path else None
    doc_url = f"{base_url}{listing.document_path}" if listing.document_path else None
    rules_url = f"{base_url}{rules_path}" if rules_path else None

    return GemForwardAuction(
        auction_id=listing.auction_id,
        title=listing.title,
        notice_path=listing.notice_path,
        notice_token=listing.notice_token,
        document_path=listing.document_path,
        document_token=listing.document_token,
        city=city,
        district=district,
        state=state,
        pincode=pincode,
        opening=opening,
        closing=closing,
        organisation=listing.organisation,
        category=detail.get("category"),
        auction_brief=detail.get("auction_brief") or listing.title,
        auction_detail=detail.get("auction_detail"),
        seller_name=detail.get("seller_name"),
        emd_required=detail.get("emd_required"),
        rules_path=rules_path,
        items=items,
        min_opening_price_inr=min(prices) if prices else None,
        detail_url=notice_url,
        document_url=doc_url,
        rules_url=rules_url,
    )
