from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scraper.discovery import run_discovery
from scraper.models import AuctionRecord, AuctionsExport, ExtractionStatus


def test_run_discovery_combines_sources_with_monkeypatched_discoverers(monkeypatch, tmp_path: Path):
    def fake_mstc(**kwargs):
        return [
            AuctionRecord(
                id="1",
                source="mstc",
                source_auction_id="1",
                auction_number="1",
                region="HO",
                office="HO",
                closing=datetime.fromisoformat("2026-07-15T10:00:00+05:30"),
                status=ExtractionStatus.LISTING_ONLY,
            )
        ], {"source": "mstc"}

    def fake_gem(**kwargs):
        return [
            AuctionRecord(
                id="gem_forward:2",
                source="gem_forward",
                source_auction_id="2",
                auction_number="2",
                region="GeM",
                office="GeM",
                closing=datetime.fromisoformat("2026-07-16T10:00:00+05:30"),
                status=ExtractionStatus.LISTING_ONLY,
            )
        ], {"source": "gem_forward"}

    monkeypatch.setattr("scraper.discovery.discover_mstc", fake_mstc)
    monkeypatch.setattr("scraper.discovery.discover_gem_forward", fake_gem)

    out = tmp_path / "discovery.json"
    export = run_discovery(
        sources=["mstc", "gem_forward"],
        out_path=out,
        min_closing_date="2026-07-10",
        allow_small_output=True,
    )

    assert isinstance(export, AuctionsExport)
    assert export.count == 2
    assert export.stats["discovery_only"] is True
    assert export.stats["by_source"] == {"mstc": 1, "gem_forward": 1}
    assert out.is_file()
