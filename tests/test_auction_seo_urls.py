from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

PUBLIC_JSON = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "auctions.json"
ROUTES_JSON = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "auction-routes.json"
OUT_SITEMAP = Path(__file__).resolve().parent.parent / "web" / "out" / "sitemap.xml"

REGRESSION_IDS = ("582972", "584985", "588051")


def _derive_route_id(auction: dict) -> str:
    source = auction.get("source") or "mstc"
    raw = (
        (auction.get("source_auction_id") or "").strip()
        or (auction.get("auction_number") or "").strip()
        or str(auction.get("id") or "").strip()
    )
    prefix = f"{source}:"
    aid = str(auction.get("id") or "")
    if aid.startswith(prefix):
        raw = aid[len(prefix) :]
    elif ":" in raw:
        raw = raw.split(":", 1)[1]
    raw = raw.strip() or aid.split(":", 1)[-1]
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", raw):
        raw = "".join(ch if re.fullmatch(r"[a-zA-Z0-9._-]", ch) else quote(ch, safe="") for ch in raw)
    return raw


def _source_slug(source: str | None) -> str:
    if source == "gem_forward":
        return "gem-forward"
    if source == "eauction":
        return "eauction"
    return "mstc"


@pytest.mark.parametrize("route_id", REGRESSION_IDS)
def test_regression_detail_path_uses_clean_route_id(route_id: str):
    if not PUBLIC_JSON.is_file() or PUBLIC_JSON.stat().st_size < 10:
        pytest.skip("auctions.json missing or empty")
    try:
        data = json.loads(PUBLIC_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pytest.skip("auctions.json is not valid JSON")
    match = None
    for auction in data.get("auctions", []):
        if route_id in str(auction.get("id", "")) or route_id == str(auction.get("source_auction_id", "")):
            match = auction
            break
    if match is None:
        pytest.skip(f"regression auction {route_id} aged out of current export")
    derived = _derive_route_id(match)
    assert derived == route_id, f"expected clean route_id {route_id}, got {derived}"
    assert ":" not in derived


def test_auction_routes_json_when_present():
    if not ROUTES_JSON.is_file():
        pytest.skip("auction-routes.json not generated yet")
    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    routes = data.get("routes") or []
    assert len(routes) >= 100
    for route in routes[:50]:
        assert route.get("route_id")
        assert ":" not in str(route["route_id"])
        assert route.get("source_slug") in {"mstc", "gem-forward", "eauction"}


def test_sitemap_when_built():
    if not OUT_SITEMAP.is_file():
        pytest.skip("sitemap not built yet")
    xml = OUT_SITEMAP.read_text(encoding="utf-8")
    assert "scrapauctionindia.com" in xml
    assert "?q=" not in xml
    assert re.search(r"/mstc/[A-Za-z0-9._-]+/", xml), "sitemap missing any MSTC detail URL"
