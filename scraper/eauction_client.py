from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper.config import REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

EAUCTION_BASE = "https://eauction.gov.in"
EAUCTION_LISTING_PATH = "/eAuction/app?page=FrontEndEauctionByDate&service=page"
EAUCTION_STATUS_PATH = "/eAuction/app?page=FrontEndEauctionStatus&service=page"
EAUCTION_FORM_ID = "ListAuctionsbyDate"

CLOSING_TABS = (
    "closingTodayTab",
    "closingWeekTab",
    "closingTwoWeekTab",
)

ALLOWED_TABS = CLOSING_TABS


class EauctionTransportError(Exception):
    pass


class EauctionClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            }
        )
        self._last_listing_url: str | None = None

    def fetch_listing_page(self, *, tab: str | None = None) -> tuple[int, str, str]:
        url = urljoin(EAUCTION_BASE, EAUCTION_LISTING_PATH)
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        final_url = resp.url
        html = resp.text
        self._last_listing_url = final_url

        if tab and tab in CLOSING_TABS:
            posted = self.post_closing_tab(tab, html=html, base_url=final_url)
            if posted is not None:
                status, html, final_url = posted

        return resp.status_code, html, final_url

    def post_closing_tab(
        self,
        tab: str,
        *,
        html: str | None = None,
        base_url: str | None = None,
    ) -> tuple[int, str, str] | None:
        if html is None:
            status, html, base_url = self.fetch_listing_page()
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", id=EAUCTION_FORM_ID)
        if not form:
            logger.warning("Tapestry form %s not found", EAUCTION_FORM_ID)
            return None

        payload = {
            inp.get("name"): inp.get("value", "")
            for inp in form.find_all("input")
            if inp.get("name")
        }
        payload["submitmode"] = "normal"
        payload["submitname"] = tab
        action = urljoin(base_url or EAUCTION_BASE, form.get("action") or "")
        resp = self.session.post(action, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        self._last_listing_url = resp.url
        return resp.status_code, resp.text, resp.url

    def fetch_pagination_page(self, href: str) -> tuple[int, str, str]:
        url = urljoin(EAUCTION_BASE, href)
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return resp.status_code, resp.text, resp.url

    def fetch_detail_page(self, detail_url: str) -> tuple[int, str]:
        resp = self.session.get(detail_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return resp.status_code, resp.text

    def detect_blockers(self, html: str) -> list[str]:
        """Detect active blockers. Captcha JS on ByDate page is not a blocker."""
        soup = BeautifulSoup(html, "html.parser")
        blockers: list[str] = []

        captcha_input = soup.find("input", attrs={"name": re.compile(r"captcha", re.I)})
        if captcha_input and captcha_input.get("type", "").lower() != "hidden":
            blockers.append("captcha")

        lower = html.lower()
        if "access denied" in lower or "forbidden" in lower:
            blockers.append("access_denied")
        if re.search(r"<form[^>]*login|password[\s\"'=]", lower) and "login" in lower:
            blockers.append("login_required")
        return blockers

    def discover_pagination_links(self, html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[dict[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "TablePages.linkPage" in href or "TablePages.linkFwd" in href:
                links.append(
                    {
                        "label": anchor.get_text(" ", strip=True),
                        "href": urljoin(EAUCTION_BASE, href),
                    }
                )
        return links

    def discover_closing_tabs(self, html: str) -> list[str]:
        return [tab for tab in CLOSING_TABS if tab in html]
