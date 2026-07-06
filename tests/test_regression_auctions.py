from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper.display_enrichment import apply_display_enrichment
from scraper.models import AuctionRecord

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "regression_auctions.json"
PUBLIC_JSON = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "auctions.json"
OUT_JSON = Path(__file__).resolve().parent.parent / "web" / "out" / "data" / "auctions.json"


def _load_regression_specs() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _find_in_export(auction_id: str, path: Path) -> dict | None:
    if not path.is_file() or path.stat().st_size < 10:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    for auction in data.get("auctions", []):
        if str(auction.get("id")) == auction_id:
            return auction
    return None


@pytest.mark.parametrize("spec", _load_regression_specs(), ids=lambda s: s["id"])
def test_regression_auction_in_export_when_data_present(spec: dict):
    raw = _find_in_export(spec["id"], PUBLIC_JSON) or _find_in_export(spec["id"], OUT_JSON)
    if raw is None:
        pytest.skip("export JSON empty or auction not in local dataset")

    record = AuctionRecord.model_validate(raw)
    enriched = apply_display_enrichment(record)

    if spec.get("require_display_title"):
        assert enriched.display_title
    for fragment in spec.get("require_display_title_contains", []):
        assert fragment in (enriched.display_title or "")
    if city := spec.get("require_location_city"):
        assert enriched.display_location_city == city
    if mat := spec.get("require_material"):
        assert enriched.display_material_category == mat
    if spec.get("require_import_timestamp"):
        assert enriched.imported_at or enriched.first_seen_at


def test_regression_fixture_file_has_core_mstc_ids():
    ids = {s["id"] for s in _load_regression_specs()}
    assert "582972" in ids
    assert "584985" in ids
    assert "588051" in ids
