from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper.ai_extractor import (
    extract_lot_with_ai,
    is_ai_fallback_enabled,
    should_use_ai,
)
from scraper.models import AuctionRecord, LotRecord


@pytest.fixture(autouse=True)
def clear_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_no_api_key_skips():
    assert is_ai_fallback_enabled() is False
    assert extract_lot_with_ai("lot text", {"auction_id": "1"}) == {}


def test_should_use_ai_on_low_confidence():
    auction = AuctionRecord(
        id="1",
        auction_number="1",
        region="JPR",
        office="JPR",
        parse_confidence="minimal",
        lots=[],
    )
    with patch("scraper.ai_extractor.OPENROUTER_API_KEY", "test-key"):
        assert should_use_ai(auction) is True


@patch("scraper.ai_extractor.OPENROUTER_API_KEY", "test-key")
@patch("scraper.ai_extractor._call_openrouter")
def test_valid_json_parses(mock_call):
    mock_call.return_value = {
        "item_title": "Scrap lot",
        "start_price_inr": 1200.0,
        "price_parse_status": "numeric",
    }
    result = extract_lot_with_ai("raw lot", {"auction_id": "99"}, lot_id="1", pdf_hash="abc123")
    assert result["item_title"] == "Scrap lot"
    assert result["start_price_inr"] == 1200.0


@patch("scraper.ai_extractor.OPENROUTER_API_KEY", "test-key")
@patch("scraper.ai_extractor._call_openrouter")
def test_invalid_json_fails_gracefully(mock_call):
    mock_call.return_value = {"start_price_inr": "not-a-number"}
    result = extract_lot_with_ai("raw lot", {"auction_id": "99"}, lot_id="1", pdf_hash="badjson")
    assert result == {}


@patch("scraper.ai_extractor.OPENROUTER_API_KEY", "test-key")
@patch("scraper.ai_extractor._call_openrouter")
def test_cache_hit_avoids_call(mock_call, tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.ai_extractor.AI_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "99_1_cached_v1_lot.json"
    cache_file.write_text(
        json.dumps({"item_title": "Cached lot", "start_price_inr": 500.0}),
        encoding="utf-8",
    )
    with patch("scraper.ai_extractor._cache_path", return_value=cache_file):
        result = extract_lot_with_ai("ignored", {"auction_id": "99"}, lot_id="1", pdf_hash="cached")
    assert result["item_title"] == "Cached lot"
    mock_call.assert_not_called()


@patch("scraper.ai_extractor.OPENROUTER_API_KEY", "test-key")
@patch("scraper.ai_extractor._call_openrouter")
def test_ai_does_not_overwrite_existing_price(mock_call):
    mock_call.return_value = {"start_price_inr": 9999.0, "item_title": "New title"}
    existing = LotRecord(
        lot_id="1",
        item_title="Old title",
        start_price_inr=1500.0,
        start_price=1500.0,
        price_parse_status="numeric",
    )
    result = extract_lot_with_ai(
        "raw",
        {"auction_id": "1"},
        lot_id="1",
        pdf_hash="merge",
        existing=existing,
    )
    assert result.get("start_price_inr", existing.start_price_inr) == 1500.0
    assert result.get("item_title", existing.item_title) == "Old title"
