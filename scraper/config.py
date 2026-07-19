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
# GeM Forward xStatus codes (hidden #xStatus on forwardauction.gem.gov.in/eprocure/home):
#   "6" = Live / Ongoing (homepage "Live (N)" — full public set; USE THIS for discovery)
#   "2" = narrower subset (~¼ of Live); DO NOT use for discovery (misses pre-bid / PQ / EMD lots)
#   "3" = Closed
GEM_FORWARD_STATUS_LIVE = "6"
GEM_FORWARD_STATUS_CLOSED = "3"
# Safety net: Live (6) is typically 400–600+. Status "2" returns ~100–150 and must fail loud.
GEM_FORWARD_LIVE_MIN_COUNT = 250
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
DEFAULT_RAW_DIR = REPO_ROOT / "work" / "raw"
DEFAULT_PIPELINE_LEDGER = REPO_ROOT / "work" / "pipeline_ledger.json"
# Download job default (MSTC deep work per run). Steady-state 100 kept for ops docs.
PIPELINE_DOWNLOAD_CAP_CATCHUP = 2000
PIPELINE_DOWNLOAD_CAP_STEADY = 100
# Process 1 download drain: auctions per batch (Hostinger PDF flush cadence matches this).
PIPELINE_DOWNLOAD_BATCH_SIZE = 25
# Max batches per download drain job (2000 / 25 = 80).
PIPELINE_DOWNLOAD_MAX_BATCHES = 80
# Hostinger mid-run PDF flush every N successful catalogue PDFs.
PIPELINE_PDF_PUSH_EVERY = 25
PIPELINE_PARSE_CAP_DEFAULT = 100
PIPELINE_DRAIN_MAX_CYCLES = 25
PIPELINE_DRAIN_PARSE_RETRIES = 3
PIPELINE_DRAIN_DEPLOY_RETRIES = 3
PIPELINE_DOWNLOAD_AUTO_RETRIES_PER_SLOT = 2

# Six independent GHA lanes
DOWNLOAD_SUCCESS_PAUSE_SEC = float(os.getenv("DOWNLOAD_SUCCESS_PAUSE_SEC", "5"))
PIPELINE_DISCOVER_MSTC_CAP = int(os.getenv("PIPELINE_DISCOVER_MSTC_CAP", "2000"))
PIPELINE_DISCOVER_GEM_CAP = int(os.getenv("PIPELINE_DISCOVER_GEM_CAP", "2000"))
PIPELINE_JOB_TIMEBOX_MIN = int(os.getenv("PIPELINE_JOB_TIMEBOX_MIN", "330"))
DOWNLOAD_FAIL_BUDGET_PCT = float(os.getenv("DOWNLOAD_FAIL_BUDGET_PCT", "0.02"))
DOWNLOAD_FAIL_BUDGET_ABS = int(os.getenv("DOWNLOAD_FAIL_BUDGET_ABS", "25"))
PARSE_FAIL_BUDGET_PCT = float(os.getenv("PARSE_FAIL_BUDGET_PCT", "0.01"))
PARSE_FAIL_BUDGET_ABS = int(os.getenv("PARSE_FAIL_BUDGET_ABS", "20"))
PIPELINE_ACTIVE_SOURCES = ("mstc", "gem_forward")
DEFAULT_PARSED_DIR = REPO_ROOT / "work" / "parsed"
PARSER_CACHE_VERSION = os.getenv("PARSER_CACHE_VERSION", "1")
TELEGRAM_NOOP_SILENT = os.getenv("TELEGRAM_NOOP_SILENT", "1").strip() not in {
    "0",
    "false",
    "no",
}
