from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from scraper.config import (
    GEM_FORWARD_BASE_URL,
    GEM_FORWARD_HOME_PATH,
    GEM_FORWARD_MODULE_TYPE,
    GEM_FORWARD_PER_PAGE,
    GEM_FORWARD_SEARCH_PATH,
    GEM_FORWARD_SEARCH_TYPE,
    GEM_FORWARD_SITE_URL,
    GEM_FORWARD_STATUS_LIVE,
    HOSTINGER_HOST,
    HOSTINGER_PORT,
    HOSTINGER_SSH_KEY,
    HOSTINGER_USERNAME,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

_CSRF_META_RE = re.compile(r'name="_csrf"\s+content="([^"]+)"', re.I)
_CSRF_INPUT_RE = re.compile(r'name="_csrf"\s+value="([^"]+)"', re.I)


class GemForwardTransportError(RuntimeError):
    pass


@dataclass
class GemForwardSession:
    csrf_token: str
    cookies: dict[str, str]
    transport: str


class _SshCurlTransport:
    """Run curl on Hostinger VPS when GeM blocks non-India IPs."""

    def __init__(self) -> None:
        host = os.getenv("HOSTINGER_HOST", HOSTINGER_HOST).strip()
        port = os.getenv("HOSTINGER_PORT", str(HOSTINGER_PORT)).strip()
        username = os.getenv("HOSTINGER_USERNAME", HOSTINGER_USERNAME).strip()
        ssh_key = os.path.expanduser(os.getenv("HOSTINGER_SSH_KEY", HOSTINGER_SSH_KEY).strip())
        if not all([host, port, username, ssh_key]):
            raise GemForwardTransportError(
                "GeM Forward is unreachable directly; set HOSTINGER_HOST, HOSTINGER_PORT, "
                "HOSTINGER_USERNAME, and HOSTINGER_SSH_KEY for SSH fallback."
            )
        self._ssh_base = [
            "ssh",
            "-i",
            ssh_key,
            "-p",
            port,
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "BatchMode=yes",
            f"{username}@{host}",
        ]
        self._cookie_file = "/tmp/gem_forward_cookies.txt"

    def _remote(self, script: str) -> str:
        cmd = self._ssh_base + [script]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="latin-1",
            errors="replace",
            timeout=REQUEST_TIMEOUT + 20,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise GemForwardTransportError(f"SSH curl failed: {stderr or result.stdout}")
        return result.stdout

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        header_args = " ".join(f"-H {shlex.quote(f'{k}: {v}')}" for k, v in (headers or {}).items())
        script = (
            f"curl -sL -m {REQUEST_TIMEOUT} -A {shlex.quote(USER_AGENT)} "
            f"-b {shlex.quote(self._cookie_file)} -c {shlex.quote(self._cookie_file)} "
            f"{header_args} {shlex.quote(url)}"
        )
        return self._remote(script)

    def post(self, url: str, *, data: dict[str, str], headers: dict[str, str] | None = None) -> str:
        header_args = " ".join(f"-H {shlex.quote(f'{k}: {v}')}" for k, v in (headers or {}).items())
        body = "&".join(f"{requests.utils.quote(str(k))}={requests.utils.quote(str(v))}" for k, v in data.items())
        script = (
            f"curl -sL -m {REQUEST_TIMEOUT} -A {shlex.quote(USER_AGENT)} "
            f"-b {shlex.quote(self._cookie_file)} -c {shlex.quote(self._cookie_file)} "
            f"-X POST {header_args} -d {shlex.quote(body)} {shlex.quote(url)}"
        )
        return self._remote(script)


class GemForwardClient:
    """HTTP client for GeM Forward Auction portal."""

    def __init__(self, transport: str = "auto") -> None:
        self._transport_mode = transport
        self._session: requests.Session | None = None
        self._ssh: _SshCurlTransport | None = None
        self._active_transport = "direct"
        self._csrf_token: str | None = None
        self._cookies: dict[str, str] = {}

    @property
    def base_url(self) -> str:
        return GEM_FORWARD_BASE_URL.rstrip("/")

    def _ensure_direct(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": USER_AGENT})
        return self._session

    def _ensure_ssh(self) -> _SshCurlTransport:
        if self._ssh is None:
            self._ssh = _SshCurlTransport()
        return self._ssh

    def _extract_csrf(self, html: str) -> str:
        match = _CSRF_META_RE.search(html) or _CSRF_INPUT_RE.search(html)
        if not match:
            raise ValueError("CSRF token not found in GeM Forward home page")
        return match.group(1)

    def _absolute_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if path.startswith("/eprocure/"):
            return urljoin(GEM_FORWARD_SITE_URL, path)
        return urljoin(GEM_FORWARD_BASE_URL + "/", path.lstrip("/"))

    def _direct_get(self, path: str) -> str:
        url = self._absolute_url(path)
        resp = self._ensure_direct().get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        self._cookies.update(resp.cookies.get_dict())
        return resp.text

    def _direct_post(self, path: str, data: dict[str, str]) -> str:
        url = self._absolute_url(path)
        headers = {}
        if self._csrf_token:
            headers["X-CSRF-TOKEN"] = self._csrf_token
        resp = self._ensure_direct().post(url, data=data, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        self._cookies.update(resp.cookies.get_dict())
        return resp.text

    def _ssh_get(self, path: str) -> str:
        url = self._absolute_url(path)
        return self._ensure_ssh().get(url)

    def _ssh_post(self, path: str, data: dict[str, str]) -> str:
        url = self._absolute_url(path)
        headers = {"X-CSRF-TOKEN": self._csrf_token} if self._csrf_token else {}
        return self._ensure_ssh().post(url, data=data, headers=headers)

    def _fetch(self, method: str, path: str, data: dict[str, str] | None = None) -> str:
        if self._active_transport == "ssh" or self._transport_mode == "ssh":
            self._active_transport = "ssh"
            if method == "GET":
                return self._ssh_get(path)
            return self._ssh_post(path, data or {})

        if self._transport_mode == "direct":
            if method == "GET":
                return self._direct_get(path)
            return self._direct_post(path, data or {})

        # auto: try direct once, fall back to SSH on connection/TLS errors
        try:
            if method == "GET":
                text = self._direct_get(path)
            else:
                text = self._direct_post(path, data or {})
            self._active_transport = "direct"
            return text
        except (requests.RequestException, OSError) as exc:
            logger.warning("Direct GeM Forward request failed (%s); using SSH fallback", exc)
            self._active_transport = "ssh"
            if method == "GET":
                return self._ssh_get(path)
            return self._ssh_post(path, data or {})

    def init_session(self) -> GemForwardSession:
        html = self._fetch("GET", GEM_FORWARD_HOME_PATH)
        self._csrf_token = self._extract_csrf(html)
        return GemForwardSession(
            csrf_token=self._csrf_token,
            cookies=dict(self._cookies),
            transport=self._active_transport,
        )

    def search_auctions_html(
        self,
        *,
        page: int = 1,
        per_page: int = GEM_FORWARD_PER_PAGE,
        status: str = GEM_FORWARD_STATUS_LIVE,
        keyword: str = "",
        category_id: str = "",
        state_id: str = "",
    ) -> str:
        if not self._csrf_token:
            self.init_session()
        data = {
            "_csrf": self._csrf_token or "",
            "keywrdSearch": keyword,
            "moduleType": GEM_FORWARD_MODULE_TYPE,
            "searchType": GEM_FORWARD_SEARCH_TYPE,
            "currentPage": str(page),
            "totalPages": "",
            "xStatus": status,
            "perPage": str(per_page),
            "stateID": state_id,
            "districtID": "",
            "cityID": "",
            "pincode": "",
            "catID": category_id,
            "deptID": "",
            "lstType": "1",
            "verField": "",
            "strDate": "",
            "location": "",
            "farmerName": "",
        }
        return self._fetch("POST", GEM_FORWARD_SEARCH_PATH, data)

    def get_html(self, path: str) -> str:
        if not self._csrf_token:
            self.init_session()
        return self._fetch("GET", path)

    def probe_connectivity(self) -> dict[str, Any]:
        session = self.init_session()
        listing_html = self.search_auctions_html(page=1, per_page=1)
        return {
            "reachable": True,
            "transport": session.transport,
            "csrf_present": bool(session.csrf_token),
            "listing_bytes": len(listing_html),
            "listing_has_records": "recordCount" in listing_html,
        }
