from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.pipeline_ledger import (
    MAX_STAGE_ATTEMPTS,
    LedgerItem,
    empty_ledger,
    estimated_download_runs_to_clear,
    mark_download,
    mark_parse,
    select_for_download,
    select_for_parse,
    write_ledger,
    load_ledger,
)
from scraper.raw_store import has_raw_html, load_raw_html, save_raw_html

IST = ZoneInfo("Asia/Kolkata")


def test_raw_html_roundtrip(tmp_path: Path):
    path = save_raw_html("mstc", "582972", "<html>ok</html>", raw_dir=tmp_path)
    assert path.is_file()
    assert has_raw_html("mstc", "582972", raw_dir=tmp_path)
    assert load_raw_html("mstc", "582972", raw_dir=tmp_path) == "<html>ok</html>"


def test_ledger_select_download_respects_cap(tmp_path: Path):
    ledger = empty_ledger()
    for i, score in enumerate([10, 90, 50, 80]):
        ledger.items.append(
            LedgerItem(
                stable_key=f"mstc:{i}",
                source="mstc",
                source_auction_id=str(i),
                download="pending",
                parse="pending",
                priority_score=score,
                first_queued_at=datetime.now(IST).isoformat(),
                updated_at=datetime.now(IST).isoformat(),
            )
        )
    selected = select_for_download(ledger, limit=2)
    assert [s.stable_key for s in selected] == ["mstc:1", "mstc:3"]
    assert estimated_download_runs_to_clear(ledger, cap=2) == 2


def test_ledger_mark_download_and_parse_retries(tmp_path: Path):
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="pending",
            parse="pending",
            first_queued_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:1", ok=True, raw_html_path="raw/mstc/1.html", pdf_path="pdfs/1.pdf")
    item = ledger.by_key()["mstc:1"]
    assert item.download == "done"
    assert item.parse == "pending"

    selected = select_for_parse(ledger)
    assert [s.stable_key for s in selected] == ["mstc:1"]

    mark_parse(ledger, "mstc:1", ok=False, error="boom")
    assert ledger.by_key()["mstc:1"].parse == "failed"

    for _ in range(MAX_STAGE_ATTEMPTS):
        mark_parse(ledger, "mstc:1", ok=False, error="boom")
    assert ledger.by_key()["mstc:1"].parse == "blocked"
    assert select_for_parse(ledger) == []

    path = write_ledger(ledger, tmp_path / "pipeline_ledger.json")
    loaded = load_ledger(path)
    assert loaded.by_key()["mstc:1"].download == "done"


def test_mark_download_resets_parse_when_redownloaded():
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:9",
            source="mstc",
            source_auction_id="9",
            download="done",
            parse="done",
            deploy_ready=True,
            first_queued_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:9", ok=True, pdf_path="pdfs/9.pdf")
    item = ledger.by_key()["mstc:9"]
    assert item.parse == "pending"
    assert item.deploy_ready is False
