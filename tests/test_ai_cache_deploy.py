"""Tests for AI cache archive sync and deploy-time hydration wiring."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from scraper.ai_enrichment.cache_sync import (
    _archive_cache,
    _extract_cache,
    default_remote_cache_archive_path,
)
from scraper.ai_enrichment.hydrate import hydrate_auctions_export
from scraper.finalize_public_export import finalize_public_export
from scraper.models import AuctionRecord, LotRecord


def _auction(**kwargs) -> AuctionRecord:
    defaults = {
        "id": "582972",
        "auction_number": "MSTC/582972",
        "region": "LKO",
        "office": "LKO",
        "state": "Uttar Pradesh",
        "location": "CIVIL LINE BALLIA",
        "item_summary": "Tower Parts; Earthwire; ACSR Dog CONDUCTOR",
        "lots": [
            LotRecord(lot_id="1", item_title="Tower Parts", quantity="430353", unit="KG"),
            LotRecord(lot_id="2", item_title="Earthwire 7/3.15mm", quantity="28800", unit="KG"),
        ],
    }
    defaults.update(kwargs)
    return AuctionRecord(**defaults)


def test_default_remote_cache_archive_path_uses_private_state_dir():
    path = default_remote_cache_archive_path("/home/user/domains/example.com/public_html/auctions")
    assert path.endswith("/ai_enrichment_state/cache.tar.gz")
    assert "public_html" not in path


def test_cache_archive_roundtrip(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "_done_registry.json").write_text('{"version":1,"items":{}}\n', encoding="utf-8")
    (cache_dir / "mstc_1_abc_prompt.json").write_text('{"status":"ready"}\n', encoding="utf-8")

    archive = tmp_path / "cache.tar.gz"
    archived = _archive_cache(cache_dir, archive)
    assert archived == 2

    target = tmp_path / "restored"
    extracted = _extract_cache(archive, target)
    assert extracted == 2
    assert (target / "mstc_1_abc_prompt.json").is_file()


def test_finalize_public_export_hydrates_ready_cache(tmp_path: Path, monkeypatch):
    from scraper.ai_enrichment import queue as ai_queue
    from scraper.ai_enrichment.schema import AI_SCHEMA_VERSION, PROMPT_VERSION

    cache_dir = tmp_path / "ai_cache"
    record = _auction(id="mstc:hydrate-live", item_summary="Copper cable scrap lot")
    cached = {
        "status": "ready",
        "input_hash": ai_queue.compute_input_hash(record),
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "model": "mock/enrichment-v1",
        "generated_at": "2026-07-09T12:00:00+05:30",
        "confidence": "high",
        "listing": {
            "clean_heading": "Copper Cable Scrap Lot",
            "buyer_summary": "Cable scrap near Ballia, Uttar Pradesh.",
            "clean_location_label": "Ballia, Uttar Pradesh",
            "location_confidence": "high",
            "material_tags": ["cable_scrap"],
            "buyer_intent_tags": [],
            "risk_notes": [],
            "lots": [{"lot_id": "1", "heading": "Tower Parts", "confidence": "high", "tags": []}],
        },
        "lots": [],
    }
    input_hash = cached["input_hash"]
    cache_path = ai_queue.write_cache(record.id, input_hash, cached, cache_dir=cache_dir)
    ai_queue.mark_ai_done(
        record,
        input_hash=input_hash,
        cache_path=cache_path,
        cache_dir=cache_dir,
    )

    json_path = tmp_path / "auctions.json"
    export = {"count": 1, "auctions": [record.model_dump(mode="json")], "stats": {}}
    json_path.write_text(json.dumps(export), encoding="utf-8")

    monkeypatch.setattr(
        "scraper.finalize_public_export.AI_ENRICHMENT_CACHE_DIR",
        cache_dir,
    )
    finalized = finalize_public_export(json_path=json_path, history_path=tmp_path / "history.json")
    auction = finalized["auctions"][0]
    assert auction["ai_status"] == "ready"
    assert auction["ai_clean_heading"] == "Copper Cable Scrap Lot"
    assert finalized["stats"]["ai_enrichment"]["ready"] == 1
