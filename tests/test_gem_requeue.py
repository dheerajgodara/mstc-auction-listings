"""GeM stale-requeue must be ledger-version gated (not empty local parsed/)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.config import PARSER_CACHE_VERSION
from scraper.pipeline_ledger import LedgerItem, empty_ledger
from scraper.pipeline_parse_assets import (
    _requeue_stale_gem_parses,
    merge_parse_queue_with_gem_upgrades,
)

IST = ZoneInfo("Asia/Kolkata")


def _gem(
    aid: str,
    *,
    parser_version: str | None,
    parse: str = "done",
    days_ahead: int = 30,
) -> LedgerItem:
    closing = (datetime.now(IST) + timedelta(days=days_ahead)).isoformat()
    return LedgerItem(
        stable_key=f"gem_forward:{aid}",
        source="gem_forward",
        source_auction_id=aid,
        download="done",
        parse=parse,
        hostinger_doc_path=f"docs/gem/{aid}.pdf",
        object_doc_url=f"https://files.csmg.in/docs/gem/{aid}.pdf",
        parser_version=parser_version,
        closing=closing,
        first_seen_at=datetime.now(IST).isoformat(),
        updated_at=datetime.now(IST).isoformat(),
    )


def _mstc_pending(aid: str) -> LedgerItem:
    return LedgerItem(
        stable_key=f"mstc:{aid}",
        source="mstc",
        source_auction_id=aid,
        download="done",
        parse="pending",
        hostinger_doc_path=f"pdfs/{aid}.pdf",
        object_doc_url=f"https://files.csmg.in/pdfs/{aid}.pdf",
        closing=(datetime.now(IST) + timedelta(days=30)).isoformat(),
        first_seen_at=datetime.now(IST).isoformat(),
        updated_at=datetime.now(IST).isoformat(),
    )


def test_no_requeue_when_ledger_already_current_version():
    ledger = empty_ledger()
    for i in range(5):
        ledger.items.append(_gem(str(1000 + i), parser_version=str(PARSER_CACHE_VERSION)))
    selected, skipped = _requeue_stale_gem_parses(ledger, max_requeue=40)
    assert selected == []
    assert skipped == 5
    assert all(i.parse == "done" for i in ledger.items)


def test_requeue_old_version_capped_and_marks_pending():
    ledger = empty_ledger()
    for i in range(10):
        ledger.items.append(_gem(str(2000 + i), parser_version="3"))
    selected, skipped = _requeue_stale_gem_parses(
        ledger, target_version="4", max_requeue=3
    )
    assert skipped == 0
    assert len(selected) == 3
    assert all(i.parse == "pending" for i in selected)
    assert sum(1 for i in ledger.items if i.parse == "pending") == 3
    assert sum(1 for i in ledger.items if i.parse == "done") == 7


def test_merge_appends_gem_upgrades_after_mstc_pending():
    mstc = [_mstc_pending("1"), _mstc_pending("2")]
    gem_up = [_gem("9", parser_version="3"), _gem("10", parser_version="3")]
    for g in gem_up:
        g.parse = "pending"
    merged = merge_parse_queue_with_gem_upgrades(mstc, gem_up)
    assert [i.stable_key for i in merged] == [
        "mstc:1",
        "mstc:2",
        "gem_forward:9",
        "gem_forward:10",
    ]


def test_merge_dedupes_already_pending_gem():
    pending = [_mstc_pending("1"), _gem("9", parser_version=None, parse="pending")]
    upgrades = [_gem("9", parser_version="3"), _gem("10", parser_version="3")]
    for g in upgrades:
        g.parse = "pending"
    merged = merge_parse_queue_with_gem_upgrades(pending, upgrades)
    keys = [i.stable_key for i in merged]
    assert keys == ["mstc:1", "gem_forward:9", "gem_forward:10"]
    assert keys.count("gem_forward:9") == 1


def test_completed_upgrade_never_requeues_again():
    """After mark_parse stamps target version, same item is skipped forever for that target."""
    from scraper.pipeline_ledger import empty_ledger, mark_parse

    ledger = empty_ledger()
    item = _gem("555", parser_version="3")
    ledger.items.append(item)
    selected, _ = _requeue_stale_gem_parses(ledger, target_version="4", max_requeue=40)
    assert len(selected) == 1
    assert selected[0].parse == "pending"

    mark_parse(
        ledger,
        item.stable_key,
        ok=True,
        lots_count=1,
        parsed_path="parsed/gem_forward/555.json",
        parser_version="4",
    )
    assert item.parse == "done"
    assert item.parser_version == "4"

    selected2, skipped2 = _requeue_stale_gem_parses(
        ledger, target_version="4", max_requeue=40
    )
    assert selected2 == []
    assert skipped2 == 1
    assert item.parse == "done"


def test_requeue_disabled_returns_empty():
    ledger = empty_ledger()
    ledger.items.append(_gem("1", parser_version="3"))
    selected, _ = _requeue_stale_gem_parses(
        ledger, target_version="4", max_requeue=40, enabled=False
    )
    assert selected == []
    assert ledger.items[0].parse == "done"
