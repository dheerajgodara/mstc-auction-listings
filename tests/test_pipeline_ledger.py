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
    # Non-MSTC pending must not burn the download cap.
    ledger.items.append(
        LedgerItem(
            stable_key="gem_forward:g1",
            source="gem_forward",
            source_auction_id="g1",
            download="pending",
            parse="pending",
            priority_score=99,
            first_queued_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    selected = select_for_download(ledger, limit=2)
    assert [s.stable_key for s in selected] == ["mstc:1", "mstc:3"]
    assert estimated_download_runs_to_clear(ledger, cap=2) == 2


def test_ledger_select_parse_prefers_mstc():
    ledger = empty_ledger()
    now = datetime.now(IST).isoformat()
    ledger.items.extend(
        [
            LedgerItem(
                stable_key="gem_forward:g1",
                source="gem_forward",
                source_auction_id="g1",
                download="done",
                parse="pending",
                hostinger_doc_path="docs/gem/g1.pdf",
                hostinger_doc_url="https://example.com/docs/gem/g1.pdf",
                priority_score=99,
                first_seen_at=now,
                updated_at=now,
            ),
            LedgerItem(
                stable_key="mstc:1",
                source="mstc",
                source_auction_id="1",
                download="done",
                parse="pending",
                hostinger_doc_path="pdfs/1.pdf",
                hostinger_doc_url="https://example.com/pdfs/1.pdf",
                priority_score=10,
                first_seen_at=now,
                updated_at=now,
            ),
        ]
    )
    selected = select_for_parse(ledger, limit=1)
    assert [s.stable_key for s in selected] == ["mstc:1"]


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
            lots_count=2,
            hostinger_doc_path="pdfs/9.pdf",
            hostinger_doc_url="https://example.com/pdfs/9.pdf",
            first_seen_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:9", ok=True, pdf_path="pdfs/9.pdf")
    item = ledger.by_key()["mstc:9"]
    assert item.parse == "pending"
    assert item.lots_count == 0


def test_select_for_download_skips_done_status_is_truth(tmp_path: Path):
    """Queue truth: done rows are never requeued; only pending (with portal URL)."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:missing",
            source="mstc",
            source_auction_id="missing",
            download="done",
            parse="done",
            portal_doc_url="https://example.com/x",
            priority_score=50,
            first_seen_at=now,
            updated_at=now,
        )
    )
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:new",
            source="mstc",
            source_auction_id="new",
            download="pending",
            parse="pending",
            portal_doc_url="https://example.com/y",
            priority_score=80,
            first_seen_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=10, pdf_dir=pdf_dir)
    assert [s.stable_key for s in selected] == ["mstc:new"]


def test_select_for_download_skips_synced_when_local_pdf_missing(tmp_path: Path):
    """Empty CI disk must not requeue Hostinger-synced durable rows."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:hostinger",
            source="mstc",
            source_auction_id="hostinger",
            download="done",
            parse="done",
            hostinger_doc_path="pdfs/hostinger.pdf",
            hostinger_doc_url="https://example.com/pdfs/hostinger.pdf",
            doc_sha256="abc",
            priority_score=99,
            first_seen_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=10, pdf_dir=pdf_dir)
    assert selected == []


def test_select_for_download_prefers_pending_over_done(tmp_path: Path):
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:done",
            source="mstc",
            source_auction_id="done",
            download="done",
            parse="pending",
            hostinger_doc_path="pdfs/done.pdf",
            hostinger_doc_url="https://example.com/pdfs/done.pdf",
            priority_score=99,
            first_seen_at=now,
            updated_at=now,
        )
    )
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:new",
            source="mstc",
            source_auction_id="new",
            download="pending",
            parse="pending",
            priority_score=1,
            first_seen_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=1)
    assert [s.stable_key for s in selected] == ["mstc:new"]

def test_select_for_download_ignores_done_phantoms(tmp_path: Path):
    """Phantoms stay done until preflight resets them — eligibility does not repair."""
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:incomplete",
            source="mstc",
            source_auction_id="incomplete",
            download="done",
            parse="pending",
            priority_score=40,
            first_seen_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=10, pdf_dir=tmp_path)
    assert selected == []


def test_select_for_download_failed_is_requeued(tmp_path: Path):
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:failed",
            source="mstc",
            source_auction_id="failed",
            download="failed",
            parse="pending",
            priority_score=10,
            first_seen_at=now,
            updated_at=now,
        )
    )
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:done",
            source="mstc",
            source_auction_id="done",
            download="done",
            parse="pending",
            hostinger_doc_path="pdfs/done.pdf",
            hostinger_doc_url="https://example.com/pdfs/done.pdf",
            priority_score=99,
            first_seen_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=10, pdf_dir=tmp_path)
    assert [s.stable_key for s in selected] == ["mstc:failed"]


def test_mark_download_sets_hostinger_fields_on_success():
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="pending",
            parse="pending",
            first_seen_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:1", ok=True, pdf_path="pdfs/1.pdf")
    item = ledger.by_key()["mstc:1"]
    assert item.download == "done"
    assert item.hostinger_doc_path == "pdfs/1.pdf"
    assert item.hostinger_doc_url


def test_mark_download_content_changed_false_preserves_parse():
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="done",
            lots_count=3,
            hostinger_doc_path="pdfs/1.pdf",
            hostinger_doc_url="https://example.com/pdfs/1.pdf",
            first_seen_at=now,
            updated_at=now,
        )
    )
    mark_download(
        ledger,
        "mstc:1",
        ok=True,
        pdf_path="pdfs/1.pdf",
        content_changed=False,
    )
    item = ledger.by_key()["mstc:1"]
    assert item.parse == "done"
    assert item.lots_count == 3


def test_mark_download_content_changed_true_resets_parse():
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="done",
            lots_count=3,
            hostinger_doc_path="pdfs/1.pdf",
            hostinger_doc_url="https://example.com/pdfs/1.pdf",
            first_seen_at=now,
            updated_at=now,
        )
    )
    mark_download(
        ledger,
        "mstc:1",
        ok=True,
        pdf_path="pdfs/1.pdf",
        content_changed=True,
    )
    item = ledger.by_key()["mstc:1"]
    assert item.parse == "pending"
    assert item.lots_count == 0


def test_mark_download_clears_hostinger_on_failure():
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="pending",
            parse="pending",
            hostinger_doc_path="pdfs/1.pdf",
            first_seen_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:1", ok=False, error="missing PDF")
    item = ledger.by_key()["mstc:1"]
    assert item.download == "pending"
    assert item.hostinger_doc_path is None
    assert item.download_error == "missing PDF"
