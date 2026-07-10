from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# MSTC endpoints
MSTC_BASE_URL = "https://www.mstcindia.co.in"
LISTING_API_PATH = "/mstcwebservice/Service.svc/getScrollMsg/{office}"
HTML_DETAIL_PATH = "/TenderEntry/Lot_Item_Details_AucID.aspx?ARID={auction_id}"
PDF_DETAIL_URL = "https://www.mstcecommerce.com/auctionhome/mstc/auction_detailed_report_pdf.jsp"
MSTC_ATTACHMENT_URL = (
    "https://www.mstcecommerce.com/auctionhome/mstc/admin/upload/downAttachedFiles.jsp"
    "?FILE_ID={filename}&doc_type={doc_type}"
)

OFFICE_CODES: list[str] = [
    "HO",
    "BBR",
    "BPL",
    "BLR",
    "CDG",
    "ERO",
    "GHY",
    "HYD",
    "JPR",
    "LKO",
    "NRO",
    "RNC",
    "RPR",
    "SRO",
    "TVC",
    "VAD",
    "BZA",
    "VZG",
    "WRO",
    "PTN",
]

REGION_TO_STATE: dict[str, str] = {
    "HO": "West Bengal",
    "BBR": "Odisha",
    "BPL": "Madhya Pradesh",
    "BLR": "Karnataka",
    "CDG": "Punjab",
    "ERO": "West Bengal",
    "GHY": "Assam",
    "HYD": "Telangana",
    "JPR": "Rajasthan",
    "LKO": "Uttar Pradesh",
    "NRO": "Delhi",
    "RNC": "Jharkhand",
    "RPR": "Chhattisgarh",
    "SRO": "Tamil Nadu",
    "TVC": "Kerala",
    "VAD": "Gujarat",
    "BZA": "Andhra Pradesh",
    "VZG": "Andhra Pradesh",
    "WRO": "Maharashtra",
    "PTN": "Bihar",
}

RETENTION_DAYS = 20
MIN_OPENING_YEAR = 2024
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SEC = 1.0
USER_AGENT = "MSTCAuctionListings/0.1 (+https://github.com; research scraper)"

# Deployment (from env — never hardcode secrets)
HOSTINGER_HOST = os.getenv("HOSTINGER_HOST", "82.25.107.163")
HOSTINGER_PORT = int(os.getenv("HOSTINGER_PORT", "65002"))
HOSTINGER_USERNAME = os.getenv("HOSTINGER_USERNAME", "u268110164")
HOSTINGER_SSH_KEY = os.getenv("HOSTINGER_SSH_KEY", "~/.ssh/cursor_mstc_auction_hostinger")
HOSTINGER_REMOTE_DIR = os.getenv(
    "HOSTINGER_REMOTE_DIR",
    "/home/u268110164/domains/scrapauctionindia.com/public_html/auctions",
)
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "")

REPO_ROOT = Path(__file__).resolve().parent.parent

# OpenRouter AI fallback (optional — used only for low-confidence extraction)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = (
    os.getenv("OPENROUTER_MODEL", "").strip()
    or "qwen/qwen3-next-80b-a3b-instruct:free"
)
_OPENROUTER_FALLBACK_MODELS_RAW = (
    os.getenv("OPENROUTER_FALLBACK_MODELS", "").strip()
    or "qwen/qwen3-next-80b-a3b-instruct:free,"
    "nvidia/nemotron-3-super-120b-a12b:free,"
    "nvidia/nemotron-nano-9b-v2:free"
)
OPENROUTER_FALLBACK_MODELS = [
    m.strip()
    for m in _OPENROUTER_FALLBACK_MODELS_RAW.split(",")
    if m.strip()
]
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "MSTC Auction Listings")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_CACHE_DIR = REPO_ROOT / "data" / "ai_cache"
AI_ENRICHMENT_CACHE_DIR = REPO_ROOT / "data" / "ai_enrichment_cache"
AI_ENRICHMENT_PROMPT_VERSION = os.getenv("AI_ENRICHMENT_PROMPT_VERSION", "2026-07-09-v1")
AI_ENRICHMENT_SCHEMA_VERSION = os.getenv("AI_ENRICHMENT_SCHEMA_VERSION", "1")
PARSER_VERSION = "v1"

# GeM Forward Auction (requires India IP or SSH fallback via Hostinger)
GEM_FORWARD_SITE_URL = "https://forwardauction.gem.gov.in"
GEM_FORWARD_BASE_URL = "https://forwardauction.gem.gov.in/eprocure"
GEM_FORWARD_HOME_PATH = "/home"
GEM_FORWARD_SEARCH_PATH = "/ajax/search-auction"
GEM_FORWARD_MODULE_TYPE = "2"
GEM_FORWARD_SEARCH_TYPE = "2"
GEM_FORWARD_STATUS_LIVE = "2"
GEM_FORWARD_PER_PAGE = 10
GEM_FORWARD_REQUEST_DELAY_SEC = 0.5
# Parent category IDs from /xcommon/ajax/parent-category-json/1
GEM_FORWARD_INCLUDE_PARENT_CATEGORIES = frozenset({23, 13, 8, 5})  # ELV, eWaste, Scrap, Machinery
GEM_FORWARD_EXCLUDE_PARENT_CATEGORIES = frozenset({2, 17})  # Land/Building, Sublet/Lease

DEFAULT_JSON_OUT = REPO_ROOT / "web" / "public" / "data" / "auctions.json"
DEFAULT_GEM_FORWARD_JSON_OUT = REPO_ROOT / "web" / "public" / "data" / "gem_forward_auctions.json"
DEFAULT_PDF_DIR = REPO_ROOT / "web" / "public" / "pdfs"
DEFAULT_DOCS_DIR = REPO_ROOT / "web" / "public" / "docs"
DEFAULT_THUMBS_DIR = REPO_ROOT / "web" / "public" / "thumbs"
