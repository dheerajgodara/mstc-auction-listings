"""Tests for AI enrichment schema, taxonomy, queue, hydrate, and mock provider."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scraper.ai_enrichment.cli import build_parser
from scraper.ai_enrichment.hydrate import build_ai_search_text, hydrate_auctions_export, merge_ai_into_auction
from scraper.ai_enrichment.ledger_sync import (
    LedgerSyncResult,
    default_remote_ledger_path,
    pull_remote_daily_usage,
)
from scraper.ai_enrichment.payload import build_listing_payload, build_enrichment_prompt, payload_stats
from scraper.ai_enrichment.provider import MockEnrichmentProvider, OpenRouterEnrichmentProvider, get_provider
from scraper.ai_enrichment.queue import (
    EnrichmentQueue,
    ai_priority,
    compute_input_hash,
    count_cache_stats,
    daily_budget_state,
    read_cache,
    read_done_cache,
    read_done_registry,
    read_daily_usage,
    select_priority_auctions,
    write_daily_usage,
)
from scraper.ai_enrichment.schema import AI_SCHEMA_VERSION, PROMPT_VERSION, validate_listing_enrichment
from scraper.ai_enrichment.taxonomy import normalize_tag, normalize_tags
from scraper.display_enrichment import apply_display_enrichment
from scraper.models import AuctionRecord, LotRecord


class _AuthFailProvider:
    last_error = "openrouter_auth_failed"

    def enrich_listing(self, record, prompt):
        return None, None


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


_FORBIDDEN_PATTERNS = [
    re.compile(r"(?:₹|rs\.?\s*|inr\s*)[\d,]+", re.I),
    re.compile(r"\b(?:emd|earnest)\b", re.I),
    re.compile(r"\b(?:https?://|www\.)", re.I),
    re.compile(r"\b(?:bid now|place bid|winning bid)\b", re.I),
]


def _assert_editorial_safe(text: str) -> None:
    for pattern in _FORBIDDEN_PATTERNS:
        assert not pattern.search(text), f"forbidden content in: {text!r}"


def test_forbidden_keys_rejected():
    raw = {
        "clean_heading": "Scrap lot",
        "buyer_summary": "Buyer-readable summary without commercial facts.",
        "location_confidence": "medium",
        "price": 1000,
    }
    result = validate_listing_enrichment(raw, expected_lot_ids={"1"})
    assert not result.ok
    assert any("forbidden_keys" in r for r in result.rejection_reasons)


def test_forbidden_commercial_content_rejected():
    raw = {
        "clean_heading": "Scrap lot",
        "buyer_summary": "Floor price ₹12,000 per MT",
        "location_confidence": "medium",
    }
    result = validate_listing_enrichment(raw, expected_lot_ids=set())
    assert not result.ok
    assert any("forbidden_commercial_content" in r for r in result.rejection_reasons)


def test_lot_id_validation_drops_unknown():
    raw = {
        "clean_heading": "Scrap lot",
        "buyer_summary": "Two lots of transmission scrap near Ballia.",
        "location_confidence": "high",
        "material_tags": ["transmission_scrap"],
        "lots": [
            {"lot_id": "1", "heading": "Tower Parts", "confidence": "high"},
            {"lot_id": "99", "heading": "Invented lot", "confidence": "high"},
        ],
    }
    result = validate_listing_enrichment(raw, expected_lot_ids={"1", "2"})
    assert result.ok
    assert result.output is not None
    assert len(result.output.lots) == 1
    assert "99" in result.dropped_lot_ids


def test_tag_normalization():
    assert normalize_tag("Transmission Scrap") == "transmission_scrap"
    assert normalize_tag("multi-lot") == "multi_lot"
    accepted, rejected = normalize_tags(["Aluminium", "unknown_tag_xyz", "large lot"])
    assert "aluminium_conductor" in accepted
    assert "large_lot" in accepted
    assert "unknown_tag_xyz" in rejected


def test_validation_limits_tags_to_two():
    raw = {
        "clean_heading": "Transmission scrap lot",
        "buyer_summary": "Transmission scrap near Ballia.",
        "location_confidence": "high",
        "material_tags": ["transmission_scrap", "aluminium_conductor", "ferrous_scrap"],
        "buyer_intent_tags": ["large_lot", "multi_lot", "documents_available"],
        "lots": [
            {
                "lot_id": "1",
                "heading": "Tower Parts",
                "summary": "Transmission tower material.",
                "tags": ["transmission_scrap", "aluminium_conductor", "ferrous_scrap"],
                "confidence": "high",
            }
        ],
    }
    result = validate_listing_enrichment(raw, expected_lot_ids={"1"})
    assert result.ok
    assert result.output is not None
    assert result.output.material_tags == ["transmission_scrap", "aluminium_conductor"]
    assert result.output.buyer_intent_tags == ["large_lot", "multi_lot"]
    assert result.output.lots[0].tags == ["transmission_scrap", "aluminium_conductor"]


def test_validation_coerces_single_string_lists():
    raw = {
        "clean_heading": "Transmission scrap lot",
        "buyer_summary": "Transmission scrap near Ballia.",
        "location_confidence": "high",
        "material_tags": "transmission_scrap",
        "buyer_intent_tags": "large_lot",
        "risk_notes": "Verify official documents before bidding.",
        "lots": [
            {
                "lot_id": "1",
                "heading": "Tower Parts",
                "summary": "Transmission tower material.",
                "tags": "transmission_scrap",
                "confidence": "high",
            }
        ],
    }
    result = validate_listing_enrichment(raw, expected_lot_ids={"1"})
    assert result.ok
    assert result.output is not None
    assert result.output.material_tags == ["transmission_scrap"]
    assert result.output.buyer_intent_tags == ["large_lot"]
    assert result.output.risk_notes == ["Verify official documents before bidding."]
    assert result.output.lots[0].tags == ["transmission_scrap"]


def test_input_hash_stable():
    record = _auction()
    h1 = compute_input_hash(record)
    h2 = compute_input_hash(record)
    assert h1 == h2
    changed = compute_input_hash(_auction(item_summary="Different summary"))
    assert changed != h1


def test_input_hash_changes_when_lot_text_changes():
    record = _auction()
    base = compute_input_hash(record)
    changed_lot = _auction(
        lots=[
            LotRecord(lot_id="1", item_title="Tower Parts REVISED", quantity="430353", unit="KG"),
            LotRecord(lot_id="2", item_title="Earthwire 7/3.15mm", quantity="28800", unit="KG"),
        ]
    )
    assert compute_input_hash(changed_lot) != base


def test_payload_compaction():
    record = _auction()
    payload = build_listing_payload(record)
    stats = payload_stats(payload)
    assert stats["lot_count"] == 2
    assert stats["all_lot_ids"] == 2
    prompt, _ = build_enrichment_prompt(record)
    assert len(prompt) <= 9000
    assert "max_material_tags" in prompt
    assert "transmission_scrap" in prompt


def test_priority_prefers_large_high_value_uncached_lots(tmp_path):
    small = _auction(id="small", item_summary="Small furniture lot", lots=[LotRecord(lot_id="1", item_title="Chair")])
    large = _auction(
        id="large",
        display_total_quantity_mt=526,
        display_material_category="transmission_scrap",
        lots=[
            LotRecord(lot_id="1", item_title="Tower Parts", quantity="430353", unit="KG"),
            LotRecord(lot_id="2", item_title="Earthwire", quantity="28800", unit="KG"),
        ],
    )
    selected, summary = select_priority_auctions([small, large], cache_dir=tmp_path, limit=1)
    assert selected[0][0].id == "large"
    assert summary["selected"] == 1
    assert "100_mt_plus" in selected[0][1]["reasons"]
    assert "high_value_material:transmission_scrap" in selected[0][1]["reasons"]


def test_priority_skips_current_cache(tmp_path):
    record = apply_display_enrichment(_auction())
    queue = EnrichmentQueue(mock=True, cache_dir=tmp_path)
    first = queue.process_auction(record)
    assert first["status"] == "ready"
    priority = ai_priority(record, tmp_path)
    assert priority["eligible"] is False
    selected, summary = select_priority_auctions([record], cache_dir=tmp_path, limit=1)
    assert selected == []
    assert summary["already_ai_done"] == 1
    assert read_done_registry(tmp_path)["items"][record.id]["status"] == "ready"


def test_mock_provider_offline():
    record = apply_display_enrichment(_auction())
    provider = MockEnrichmentProvider()
    prompt, _ = build_enrichment_prompt(record)
    raw, model = provider.enrich_listing(record, prompt)
    assert model == "mock/enrichment-v1"
    assert raw is not None
    validation = validate_listing_enrichment(raw, expected_lot_ids={"1", "2"})
    assert validation.ok


def test_mock_buyer_summary_avoids_forbidden_terms():
    record = apply_display_enrichment(
        _auction(min_start_price=50000, emd_summary="EMD ₹5,000 per lot", price_summary="Floor ₹1,00,000")
    )
    provider = MockEnrichmentProvider()
    prompt, _ = build_enrichment_prompt(record)
    raw, _ = provider.enrich_listing(record, prompt)
    assert raw is not None
    _assert_editorial_safe(raw["buyer_summary"])
    validation = validate_listing_enrichment(raw, expected_lot_ids={"1", "2"})
    assert validation.ok


def test_mock_lot_summaries_avoid_forbidden_terms():
    record = apply_display_enrichment(_auction())
    provider = MockEnrichmentProvider()
    prompt, _ = build_enrichment_prompt(record)
    raw, _ = provider.enrich_listing(record, prompt)
    assert raw is not None
    for lot in raw.get("lots") or []:
        if lot.get("summary"):
            _assert_editorial_safe(lot["summary"])
        if lot.get("heading"):
            _assert_editorial_safe(lot["heading"])


def test_get_provider_defaults_network_safe():
    provider = get_provider()
    assert isinstance(provider, MockEnrichmentProvider)


def test_get_provider_allow_network_uses_openrouter():
    provider = get_provider(allow_network=True)
    assert isinstance(provider, OpenRouterEnrichmentProvider)


def test_openrouter_provider_skips_without_allow_network():
    provider = OpenRouterEnrichmentProvider(allow_network=False)
    record = apply_display_enrichment(_auction())
    prompt, _ = build_enrichment_prompt(record)
    raw, model = provider.enrich_listing(record, prompt)
    assert raw is None
    assert model is None


def test_dry_run_report_is_network_safe(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.ai_enrichment.queue.AI_ENRICHMENT_CACHE_DIR", tmp_path)
    queue = EnrichmentQueue(dry_run=True, cache_dir=tmp_path)
    report = queue.run([_auction()], limit=1).to_dict()
    assert report["dry_run"] is True
    assert report["network_safe"] is True
    assert report["will_call_provider"] is False
    assert report["no_network"] is True
    assert report["prompt_version"] == PROMPT_VERSION
    assert report["schema_version"] == AI_SCHEMA_VERSION
    assert report["dry_run_estimate"]["processed"] == 1
    assert report["dry_run_estimate"]["max_prompt_chars"] > 0


def test_mock_no_network_creates_ready_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.ai_enrichment.queue.AI_ENRICHMENT_CACHE_DIR", tmp_path)
    record = apply_display_enrichment(_auction())
    queue = EnrichmentQueue(mock=True, no_network=True, cache_dir=tmp_path, max_requests=1)
    result = queue.process_auction(record)
    assert result["status"] == "ready"
    cached = read_cache(record.id, compute_input_hash(record), tmp_path)
    assert cached is not None
    assert cached["status"] == "ready"


def test_rejected_cache_does_not_hydrate_as_ready():
    record = _auction()
    rejected = {
        "status": "rejected",
        "input_hash": compute_input_hash(record),
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "rejection_reasons": ["forbidden_commercial_content_in_buyer_summary"],
        "listing": {
            "clean_heading": "Should not appear",
            "buyer_summary": "Floor price ₹12,000",
            "location_confidence": "medium",
        },
    }
    merged = merge_ai_into_auction(record, rejected)
    assert merged.ai_status == "rejected"
    assert merged.ai_clean_heading is None
    assert "Should not appear" not in (merged.search_text or "")


def test_cache_skip_on_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.ai_enrichment.queue.AI_ENRICHMENT_CACHE_DIR", tmp_path)
    record = apply_display_enrichment(_auction())
    provider = MockEnrichmentProvider()
    queue = EnrichmentQueue(provider=provider, mock=True, no_network=True, cache_dir=tmp_path)
    first = queue.process_auction(record)
    assert first["status"] == "ready"
    provider.enrich_listing = MagicMock(side_effect=AssertionError("provider should not be called"))
    second = queue.process_auction(record)
    assert second["status"] == "skipped"
    assert second["reason"] == "ai_done_registry"


def test_ready_ai_marks_auction_permanently_done(tmp_path):
    record = apply_display_enrichment(_auction())
    queue = EnrichmentQueue(provider=MockEnrichmentProvider(), allow_network=True, mock=False, no_network=False, cache_dir=tmp_path)
    result = queue.process_auction(record)
    assert result["status"] == "ready"

    registry = read_done_registry(tmp_path)
    assert registry["items"][record.id]["status"] == "ready"
    assert registry["items"][record.id]["cache_file"].endswith(f"_{PROMPT_VERSION}.json")
    assert read_done_cache(record, tmp_path)["status"] == "ready"


def test_done_registry_blocks_changed_input_forever(tmp_path):
    original = apply_display_enrichment(_auction(id="done1", item_summary="Original title"))
    queue = EnrichmentQueue(provider=MockEnrichmentProvider(), allow_network=True, mock=False, no_network=False, cache_dir=tmp_path)
    assert queue.process_auction(original)["status"] == "ready"

    changed = apply_display_enrichment(_auction(id="done1", item_summary="Changed title after scrape"))
    provider = MockEnrichmentProvider()
    provider.enrich_listing = MagicMock(side_effect=AssertionError("provider must not be called for done auction"))
    second_queue = EnrichmentQueue(provider=provider, allow_network=True, mock=False, no_network=False, cache_dir=tmp_path)
    result = second_queue.process_auction(changed)
    assert result["status"] == "skipped"
    assert result["reason"] == "ai_done_registry"

    priority = ai_priority(changed, tmp_path)
    assert priority["eligible"] is False
    assert priority["reasons"] == ["ai_done_registry"]


def test_hydrate_uses_done_cache_even_when_input_hash_changed(tmp_path):
    original = apply_display_enrichment(_auction(id="hydrate-done", item_summary="Original title"))
    queue = EnrichmentQueue(provider=MockEnrichmentProvider(), allow_network=True, mock=False, no_network=False, cache_dir=tmp_path)
    assert queue.process_auction(original)["status"] == "ready"

    changed = _auction(id="hydrate-done", item_summary="Changed parser title")
    cached = read_done_cache(changed, tmp_path)
    assert cached is not None
    merged = merge_ai_into_auction(changed, cached)
    assert merged.ai_status == "ready"
    assert merged.ai_clean_heading


def test_auth_failure_stops_run_without_polluting_cache(tmp_path):
    queue = EnrichmentQueue(
        provider=_AuthFailProvider(),
        allow_network=True,
        mock=False,
        no_network=False,
        cache_dir=tmp_path,
    )
    report = queue.run([_auction(id="a"), _auction(id="b")], limit=2)
    payload = report.to_dict()
    assert payload["processed"] == 1
    assert payload["failed"] == 1
    assert payload["details"][0]["reason"] == "openrouter_auth_failed"
    assert count_cache_stats(tmp_path)["total"] == 0


def test_daily_budget_blocks_provider_calls(tmp_path):
    write_daily_usage(
        {"date": read_daily_usage(tmp_path)["date"], "attempted": 2, "ready": 2, "rejected": 0, "failed": 0},
        tmp_path,
    )
    queue = EnrichmentQueue(
        provider=MockEnrichmentProvider(),
        allow_network=True,
        mock=False,
        no_network=False,
        cache_dir=tmp_path,
        daily_budget=2,
    )
    report = queue.run([_auction(id="a"), _auction(id="b")], limit=2)
    payload = report.to_dict()
    assert payload["processed"] == 0
    assert payload["skipped"] == 0
    assert payload["details"] == []
    assert payload["budget"]["remaining_today"] == 0
    assert payload["selection"]["selected"] == 0


def test_selection_summary_reports_remaining_after_budget_cap(tmp_path):
    auctions = [_auction(id=f"a{i}") for i in range(5)]
    selected, summary = select_priority_auctions(auctions, cache_dir=tmp_path, limit=2)
    assert len(selected) == 2
    assert summary["eligible"] == 5
    assert summary["selected"] == 2
    assert summary["remaining_after_selection"] == 3
    assert summary["estimated_runs_to_clear"] == 2


def test_daily_budget_updates_after_ready_call(tmp_path):
    queue = EnrichmentQueue(
        provider=MockEnrichmentProvider(),
        allow_network=True,
        mock=False,
        no_network=False,
        cache_dir=tmp_path,
        daily_budget=5,
    )
    report = queue.run([_auction(id="a")], limit=1)
    payload = report.to_dict()
    assert payload["ready"] == 1
    usage = read_daily_usage(tmp_path)
    assert usage["attempted"] == 1
    assert usage["ready"] == 1
    assert daily_budget_state(cache_dir=tmp_path, daily_budget=5)["remaining_today"] == 4


def test_default_remote_ledger_path_is_private(monkeypatch):
    monkeypatch.delenv("HOSTINGER_AI_LEDGER_PATH", raising=False)
    remote = "/home/u268110164/domains/scrapauctionindia.com/public_html/auctions"
    assert (
        default_remote_ledger_path(remote)
        == "/home/u268110164/domains/scrapauctionindia.com/ai_enrichment_state/_daily_usage.json"
    )


def test_remote_ledger_pull_reports_missing_env(tmp_path, monkeypatch):
    for key in (
        "HOSTINGER_HOST",
        "HOSTINGER_PORT",
        "HOSTINGER_USERNAME",
        "HOSTINGER_SSH_KEY",
        "HOSTINGER_REMOTE_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    result = pull_remote_daily_usage(tmp_path)
    assert result.ok is False
    assert result.action == "pull"
    assert "missing Hostinger ledger env" in result.message


def test_cli_remote_ledger_failure_fails_closed_before_provider(tmp_path, monkeypatch):
    json_path = tmp_path / "auctions.json"
    json_path.write_text(
        json.dumps({"count": 1, "auctions": [_auction().model_dump(mode="json")]}),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    provider = MockEnrichmentProvider()
    provider.enrich_listing = MagicMock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr("scraper.ai_enrichment.queue.get_provider", lambda **_kwargs: provider)
    monkeypatch.setattr(
        "scraper.ai_enrichment.cli.pull_remote_daily_usage",
        lambda _cache_dir: LedgerSyncResult(
            mode="hostinger",
            ok=False,
            action="pull",
            message="ssh unavailable",
        ),
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "--json",
            str(json_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "enrich",
            "--allow-network",
            "--ledger-sync",
            "hostinger",
            "--limit",
            "1",
            "--report-json",
            str(report_path),
        ]
    )
    assert args.func(args) == 2
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["error"] == "remote_ledger_pull_failed"
    assert payload["will_call_provider"] is False


def test_cli_sends_started_selection_and_complete_reports(tmp_path, monkeypatch):
    json_path = tmp_path / "auctions.json"
    json_path.write_text(
        json.dumps({"count": 1, "auctions": [_auction().model_dump(mode="json")]}),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    events: list[str] = []
    monkeypatch.setattr(
        "scraper.ai_enrichment.cli.send_ai_enrichment_report",
        lambda _payload, *, event="report": events.append(event) or True,
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "--json",
            str(json_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "enrich",
            "--mock",
            "--limit",
            "1",
            "--report-json",
            str(report_path),
            "--telegram-report",
        ]
    )
    assert args.func(args) == 0
    assert events == ["started", "selection_done", "complete"]
    assert report_path.with_name("report.plan.json").is_file()


def test_hydrate_merge_preserves_parser_fields(tmp_path):
    record = _auction()
    parser_title = record.item_summary
    cached = {
        "status": "ready",
        "input_hash": compute_input_hash(record),
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "model": "mock/enrichment-v1",
        "generated_at": "2026-07-09T12:00:00+05:30",
        "confidence": "high",
        "listing": {
            "clean_heading": "459 MT Transmission Scrap",
            "buyer_summary": "Transmission scrap near Ballia, Uttar Pradesh.",
            "clean_location_label": "Ballia, Uttar Pradesh",
            "location_confidence": "high",
            "material_tags": ["transmission_scrap"],
            "buyer_intent_tags": ["multi_lot"],
            "risk_notes": [],
            "lots": [
                {"lot_id": "1", "heading": "Tower Parts", "confidence": "high", "tags": []},
            ],
        },
        "lots": [],
    }
    merged = merge_ai_into_auction(record, cached)
    assert merged.item_summary == parser_title
    assert merged.ai_status == "ready"
    assert merged.ai_clean_heading == "459 MT Transmission Scrap"
    assert merged.lots[0].item_title == "Tower Parts"
    assert merged.lots[0].ai_heading == "Tower Parts"
    assert "transmission_scrap" in merged.search_text


def test_search_text_gains_ai_only_after_ready_hydrate():
    record = _auction()
    base_search = record.search_text or ""
    cached = {
        "status": "ready",
        "input_hash": compute_input_hash(record),
        "prompt_version": PROMPT_VERSION,
        "schema_version": AI_SCHEMA_VERSION,
        "model": "mock/enrichment-v1",
        "generated_at": "2026-07-09T12:00:00+05:30",
        "confidence": "high",
        "listing": {
            "clean_heading": "Unique AI Heading Token XYZ",
            "buyer_summary": "Unique AI Summary Token ABC",
            "location_confidence": "high",
            "material_tags": ["transmission_scrap"],
            "buyer_intent_tags": [],
            "risk_notes": [],
            "lots": [],
        },
    }
    merged = merge_ai_into_auction(record, cached)
    assert "unique ai heading token xyz" in merged.search_text.lower()
    assert build_ai_search_text(record) == ""
    assert "unique ai heading token xyz" not in base_search.lower()


def test_forbidden_lot_content_not_public_ready():
    raw = {
        "clean_heading": "Scrap lot",
        "buyer_summary": "Transmission scrap near Ballia.",
        "location_confidence": "high",
        "lots": [
            {
                "lot_id": "1",
                "heading": "Tower Parts",
                "summary": "EMD required before bidding",
                "confidence": "high",
            },
        ],
    }
    result = validate_listing_enrichment(raw, expected_lot_ids={"1", "2"})
    assert not result.ok
    assert any("forbidden_commercial_content" in r for r in result.rejection_reasons)


def test_hydrate_export_stats():
    record = _auction()
    export = {"count": 1, "auctions": [record.model_dump(mode="json")], "stats": {}}
    hydrated, stats = hydrate_auctions_export(export, cache_dir=Path("/nonexistent"))
    assert stats["missing"] == 1
    assert hydrated["auctions"][0]["item_summary"] == record.item_summary


def test_build_ai_search_text_only_when_ready():
    record = _auction().model_copy(
        update={
            "ai_status": "ready",
            "ai_clean_heading": "Heading",
            "ai_buyer_summary": "Summary",
        }
    )
    text = build_ai_search_text(record)
    assert "heading" in text
    missing = _auction(ai_status="missing")
    assert build_ai_search_text(missing) == ""


def test_cli_default_requires_allow_network_for_openrouter():
    parser = build_parser()
    args = parser.parse_args(["enrich", "--limit", "1"])
    assert args.allow_network is False


def test_ai_enrichment_cache_ignored_by_gitignore():
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    body = gitignore.read_text(encoding="utf-8")
    assert "data/ai_enrichment_cache/" in body or "data/" in body


def test_frontend_display_prefers_ai_only_when_ready():
    script = Path(__file__).resolve().parents[1] / "web" / "scripts" / "verify-ai-display.mjs"
    result = subprocess.run(
        ["node", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_site_loads_without_ai_fields():
    script = Path(__file__).resolve().parents[1] / "web" / "scripts" / "verify-ai-display.mjs"
    result = subprocess.run(
        ["node", str(script), "--missing-ai"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
