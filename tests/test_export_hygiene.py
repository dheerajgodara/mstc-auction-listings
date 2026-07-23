"""Tests for aged-out export hygiene, quarantine, and gate classification."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.auction_quarantine import (
    active_quarantine_keys,
    add_quarantine_entries,
    empty_quarantine,
    prune_expired,
    remove_quarantine_entries,
)
from scraper.export_hygiene import (
    apply_quarantine_skips,
    build_archive_export,
    classify_strict_errors,
    format_dropped_telegram_note,
    poison_threshold,
    strip_aged_out_auctions,
)
from scraper.incremental_materialize import materialize_incremental_export
from scraper.incremental_plan import WorkPlanItem, IncrementalWorkPlan
from scraper.pipeline_ledger import LedgerItem, empty_ledger, mark_parse
from scraper.qa_summary import run_strict_qa

IST = ZoneInfo("Asia/Kolkata")
MIN_CLOSING = "2026-07-17"


def _row(
    auction_id: str,
    *,
    closing: str,
    source: str = "mstc",
) -> dict:
    return {
        "id": auction_id,
        "source": source,
        "source_auction_id": auction_id,
        "auction_number": auction_id,
        "closing": closing,
        "item_summary": f"Lot {auction_id}",
        "lots": [{"lot_id": "1", "item_title": "x"}],
        "status": "complete",
        "parse_confidence": "high",
        "missing_fields": [],
        "errors": [],
        "region": "HO",
        "office": "HO",
    }


def _export(rows: list[dict]) -> dict:
    from collections import Counter

    by = Counter(str(r.get("source") or "unknown") for r in rows)
    return {
        "generated_at": "2026-07-16T12:00:00+05:30",
        "count": len(rows),
        "auctions": rows,
        "stats": {"by_source": dict(by)},
    }


def test_strip_aged_out_keeps_valid_and_recounts():
    rows = [_row(str(i), closing="2026-07-18T10:00:00+05:30") for i in range(100)]
    aged = [
        _row("a1", closing="2026-07-16T10:00:00+05:30"),
        _row("a2", closing="2026-07-16T11:00:00+05:30"),
        _row("a3", closing="2026-07-16T12:00:00+05:30"),
        _row("a4", closing="2026-07-16T13:00:00+05:30"),
        _row("a5", closing="2026-07-16T14:00:00+05:30"),
    ]
    result = strip_aged_out_auctions(_export(rows + aged), min_closing_date=MIN_CLOSING)
    assert len(result.dropped) == 5
    assert result.export["count"] == 100
    assert result.export["stats"]["by_source"]["mstc"] == 100


def test_strip_poison_guard():
    # 6 of 100 = 6% > 5% threshold (max(50,5)=50 wait — 6 < 50 so OK)
    # Need drop > max(50, 5%): use 60 aged of 100
    valid = [_row(str(i), closing="2026-07-18T10:00:00+05:30") for i in range(40)]
    aged = [_row(f"old{i}", closing="2026-07-16T10:00:00+05:30") for i in range(60)]
    assert poison_threshold(100) == 50
    with pytest.raises(RuntimeError, match="poison guard"):
        strip_aged_out_auctions(_export(valid + aged), min_closing_date=MIN_CLOSING)
    ok = strip_aged_out_auctions(
        _export(valid + aged),
        min_closing_date=MIN_CLOSING,
        allow_large_aged_out_strip=True,
    )
    assert len(ok.dropped) == 60
    assert ok.export["count"] == 40


def test_strip_then_strict_qa_passes(tmp_path: Path):
    rows = [
        _row(str(i), closing="2026-07-18T10:00:00+05:30", source="mstc")
        for i in range(20)
    ]
    # sprinkle eauction so require_sources not needed here - run_strict_qa without require
    aged = [_row(f"old{i}", closing="2026-07-16T10:00:00+05:30") for i in range(5)]
    result = strip_aged_out_auctions(_export(rows + aged), min_closing_date=MIN_CLOSING)
    path = tmp_path / "candidate.json"
    path.write_text(__import__("json").dumps(result.export), encoding="utf-8")
    report = run_strict_qa(path, min_count=10, min_closing_date=MIN_CLOSING)
    assert report["passed"] is True
    assert len(result.dropped) == 5


def test_classify_aged_out_vs_count_floor():
    classified = classify_strict_errors(
        [
            "record 588636 closes before 2026-07-17: 2026-07-16T10:00:00+05:30",
            "required source missing: mstc",
            "count below floor: 900 < 1000",
            "record x missing closing",
            "weird schema blowup",
        ]
    )
    assert len(classified.aged_out) == 1
    assert len(classified.missing_source) == 1
    assert len(classified.count_floor) == 1
    assert len(classified.missing_closing) == 1
    assert len(classified.schema) == 1
    assert classified.only_aged_out is False
    only = classify_strict_errors(
        ["record 1 closes before 2026-07-17: 2026-07-16T00:00:00+05:30"]
    )
    assert only.only_aged_out is True
    assert not only.fatal

def test_quarantine_skip_and_expiry():
    rows = [
        _row("1", closing="2026-07-18T10:00:00+05:30"),
        _row("2", closing="2026-07-18T10:00:00+05:30"),
        _row("3", closing="2026-07-18T10:00:00+05:30"),
    ]
    export = _export(rows)
    q = apply_quarantine_skips(export, {"mstc:2"}, min_count=2)
    assert q.export["count"] == 2
    assert [a["id"] for a in q.export["auctions"]] == ["1", "3"]

    with pytest.raises(RuntimeError, match="min_count"):
        apply_quarantine_skips(export, {"mstc:1", "mstc:2"}, min_count=2)

    data = empty_quarantine()
    data = add_quarantine_entries(
        ["mstc:2"],
        reason="operator_skip",
        source="manual",
        hours=48,
        data=data,
        push_remote=False,
    )
    assert "mstc:2" in active_quarantine_keys(data, pull_remote=False)

    past = datetime.now(IST) - timedelta(hours=1)
    data["entries"]["mstc:2"]["expires_at"] = past.isoformat()
    pruned = prune_expired(data)
    assert "mstc:2" not in pruned["entries"]

    data = add_quarantine_entries(
        ["mstc:9"],
        reason="x",
        hours=48,
        data=empty_quarantine(),
        push_remote=False,
    )
    data = remove_quarantine_entries(["mstc:9"], data=data, push_remote=False)
    assert "mstc:9" not in data["entries"]


def test_materialize_excludes_aged_out_reuse():
    previous = _export(
        [
            _row("1", closing="2026-07-16T10:00:00+05:30"),  # aged
            _row("2", closing="2026-07-18T10:00:00+05:30"),
        ]
    )
    parsed = _export([_row("3", closing="2026-07-18T11:00:00+05:30")])
    plan = IncrementalWorkPlan(
        generated_at="2026-07-16T12:00:00+05:30",
        counts={"unchanged": 2, "changed": 1, "new": 0, "removed": 0},
        action_counts={"reuse_previous": 2, "deep_parse": 1},
        by_source={"mstc": {"reuse_previous": 2, "deep_parse": 1}},
        items=[
            WorkPlanItem(
                stable_key="mstc:1",
                source="mstc",
                source_auction_id="1",
                decision="unchanged",
                action="reuse_previous",
            ),
            WorkPlanItem(
                stable_key="mstc:2",
                source="mstc",
                source_auction_id="2",
                decision="unchanged",
                action="reuse_previous",
            ),
            WorkPlanItem(
                stable_key="mstc:3",
                source="mstc",
                source_auction_id="3",
                decision="new",
                action="deep_parse",
            ),
        ],
    )
    out = materialize_incremental_export(
        work_plan=plan,
        previous_export=previous,
        parsed_export=parsed,
        min_closing_date=MIN_CLOSING,
    )
    ids = {a["id"] for a in out["auctions"]}
    assert ids == {"2", "3"}
    assert out["stats"]["incremental_materialize"]["excluded_aged_out_reuse"] == 1


def test_format_dropped_telegram_note():
    assert format_dropped_telegram_note([]) == ""
    note = format_dropped_telegram_note(
        [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    )
    assert "dropped 3 aged-out" in note
    assert "1" in note
    assert "dropped 5 aged-out" == format_dropped_telegram_note(
        [{"id": str(i)} for i in range(5)]
    )


def test_ledger_parse_not_done_until_explicit_mark():
    """Mirrors parse lifecycle: failures mark immediately; success deferred."""
    ledger = empty_ledger()
    now = datetime.now(IST).isoformat()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="pending",
            priority_score=1,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Gate fail path: never call mark_parse(ok=True)
    assert ledger.items[0].parse == "pending"
    mark_parse(ledger, "mstc:1", ok=True, lots_count=1, deploy_ready=True)
    assert ledger.items[0].parse == "done"
    assert ledger.items[0].lots_count == 1


def test_build_archive_export_keeps_shell_without_lots():
    now = datetime(2026, 7, 23, 14, 30, tzinfo=IST)
    live = _export(
        [
            _row(
                "live1",
                closing=(now + timedelta(days=2)).isoformat(),
            )
        ]
    )
    # Simulate strip dropping a same-day AIR copper lot
    stripped = strip_aged_out_auctions(
        _export(
            [
                _row("590217", closing=datetime(2026, 7, 23, 17, 0, tzinfo=IST).isoformat()),
                _row("live1", closing=(now + timedelta(days=2)).isoformat()),
            ]
        ),
        min_closing_date=(now + timedelta(hours=12)).isoformat(),
        allow_large_aged_out_strip=True,
    )
    assert any(d["id"] == "590217" for d in stripped.dropped)
    assert stripped.dropped[0].get("auction") is not None

    ledger_item = LedgerItem(
        stable_key="mstc:590217",
        source="mstc",
        source_auction_id="590217",
        closing=datetime(2026, 7, 23, 17, 0, tzinfo=IST).isoformat(),
        opening=datetime(2026, 7, 23, 12, 0, tzinfo=IST).isoformat(),
        seller="All India Radio",
        state="Rajasthan",
        detail_url="https://www.mstcindia.co.in/TenderEntry/Lot_Item_Details_AucID.aspx?ARID=590217",
        discover="done",
        download="pending",
        parse="pending",
        priority_score=10,
        first_seen_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    archive = build_archive_export(
        live_export=stripped.export,
        stripped_dropped=stripped.dropped,
        ledger_items=[ledger_item],
        discovery_by_key={
            "mstc:590217": {
                "id": "590217",
                "source": "mstc",
                "auction_number": "MSTC/JPR/All India Radio/2/Jodhpur/26-27/19431",
                "closing": datetime(2026, 7, 23, 17, 0, tzinfo=IST).isoformat(),
                "display_title": "Copper Scrap",
            }
        },
        now=now,
    )
    assert archive["count"] >= 1
    ids = {a["id"] for a in archive["auctions"]}
    assert "590217" in ids
    row = next(a for a in archive["auctions"] if a["id"] == "590217")
    assert row["in_archive"] is True
    assert row["archive_reason"] in {"under_runway", "aged_out", "closed"}
    assert row.get("catalogue_status") in {"none", "pending", "ready"}
    # Live runway row must not appear in archive
    assert "live1" not in ids


def test_build_archive_export_gc_beyond_t30():
    now = datetime(2026, 7, 23, 12, 0, tzinfo=IST)
    old = _row("old", closing=(now - timedelta(days=40)).isoformat())
    archive = build_archive_export(
        live_export=_export([]),
        stripped_dropped=[{"id": "old", "auction": old, "key": "mstc:old"}],
        ledger_items=[],
        discovery_by_key={},
        now=now,
    )
    assert archive["count"] == 0
