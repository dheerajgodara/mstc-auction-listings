from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.pipeline_ledger import (
    MAX_STAGE_ATTEMPTS,
    LedgerItem,
    empty_ledger,
    estimated_download_runs_to_clear,
    grandfather_media_synced_legacy,
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
                priority_score=99,
                first_queued_at=now,
                updated_at=now,
            ),
            LedgerItem(
                stable_key="mstc:1",
                source="mstc",
                source_auction_id="1",
                download="done",
                parse="pending",
                priority_score=10,
                first_queued_at=now,
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
            deploy_ready=True,
            first_queued_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:9", ok=True, pdf_path="pdfs/9.pdf")
    item = ledger.by_key()["mstc:9"]
    assert item.parse == "pending"
    assert item.deploy_ready is False


def test_select_for_download_requeues_done_without_valid_pdf(tmp_path: Path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    # Done but no pdf_path → must requeue (true repair).
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:missing",
            source="mstc",
            source_auction_id="missing",
            download="done",
            parse="done",
            pdf_path=None,
            priority_score=50,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Done with path but Hostinger sync owed → requeue (sync debt).
    corrupt = pdf_dir / "corrupt.pdf"
    corrupt.write_bytes(b"<html>nope</html>" + (b"x" * 2000))
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:corrupt",
            source="mstc",
            source_auction_id="corrupt",
            download="done",
            parse="pending",
            pdf_path="pdfs/corrupt.pdf",
            media_synced=False,
            priority_score=40,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Done + synced + path → skip (even if local were missing).
    good = pdf_dir / "good.pdf"
    good.write_bytes(b"%PDF-1.4\n" + (b"y" * 2000))
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:good",
            source="mstc",
            source_auction_id="good",
            download="done",
            parse="pending",
            pdf_path="pdfs/good.pdf",
            media_synced=True,
            priority_score=99,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Pending still wins priority alongside repairs.
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:new",
            source="mstc",
            source_auction_id="new",
            download="pending",
            parse="pending",
            priority_score=80,
            first_queued_at=now,
            updated_at=now,
        )
    )

    selected = select_for_download(ledger, limit=10, pdf_dir=pdf_dir)
    keys = [s.stable_key for s in selected]
    assert "mstc:good" not in keys
    # Priority: new → sync → repair
    assert keys == ["mstc:new", "mstc:corrupt", "mstc:missing"]
    assert estimated_download_runs_to_clear(ledger, cap=2, pdf_dir=pdf_dir) == 2


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
            pdf_path="pdfs/hostinger.pdf",
            media_synced=True,
            priority_score=99,
            first_queued_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=10, pdf_dir=pdf_dir)
    assert selected == []


def test_select_for_download_prefers_pending_over_sync_debt(tmp_path: Path):
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:sync",
            source="mstc",
            source_auction_id="sync",
            download="done",
            parse="pending",
            pdf_path="pdfs/sync.pdf",
            media_synced=False,
            priority_score=99,
            first_queued_at=now,
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
            first_queued_at=now,
            updated_at=now,
        )
    )
    selected = select_for_download(ledger, limit=1)
    assert [s.stable_key for s in selected] == ["mstc:new"]


def test_grandfather_media_synced_legacy_then_skip(tmp_path: Path):
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:legacy",
            source="mstc",
            source_auction_id="legacy",
            download="done",
            parse="done",
            pdf_path="pdfs/legacy.pdf",
            media_synced=None,
            priority_score=50,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Incomplete legacy (no pdf_path) stays eligible after grandfather.
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:incomplete",
            source="mstc",
            source_auction_id="incomplete",
            download="done",
            parse="pending",
            pdf_path=None,
            media_synced=None,
            priority_score=40,
            first_queued_at=now,
            updated_at=now,
        )
    )
    n = grandfather_media_synced_legacy(ledger)
    assert n == 1
    assert ledger.by_key()["mstc:legacy"].media_synced is True
    assert ledger.by_key()["mstc:incomplete"].media_synced is None
    selected = select_for_download(ledger, limit=10, pdf_dir=tmp_path)
    assert [s.stable_key for s in selected] == ["mstc:incomplete"]


def test_select_for_download_requeues_unsynced_media(tmp_path: Path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    good = pdf_dir / "ok.pdf"
    good.write_bytes(b"%PDF-1.4\n" + (b"y" * 2000))
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:ok",
            source="mstc",
            source_auction_id="ok",
            download="done",
            parse="pending",
            pdf_path="pdfs/ok.pdf",
            media_synced=False,
            priority_score=10,
            first_queued_at=now,
            updated_at=now,
        )
    )
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:synced",
            source="mstc",
            source_auction_id="synced",
            download="done",
            parse="pending",
            pdf_path="pdfs/ok.pdf",
            media_synced=True,
            priority_score=99,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Put a valid local file for synced id too
    (pdf_dir / "synced.pdf").write_bytes(b"%PDF-1.4\n" + (b"y" * 2000))
    selected = select_for_download(ledger, limit=10, pdf_dir=pdf_dir)
    assert [s.stable_key for s in selected] == ["mstc:ok"]


def test_mark_download_sets_media_synced_false_until_flush():
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
    mark_download(ledger, "mstc:1", ok=True, pdf_path="pdfs/1.pdf")
    item = ledger.by_key()["mstc:1"]
    assert item.download == "done"
    assert item.media_synced is False


def test_mark_download_content_changed_false_preserves_parse_and_sync():
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="done",
            deploy_ready=True,
            pdf_path="pdfs/1.pdf",
            media_synced=True,
            media_synced_at=now,
            first_queued_at=now,
            updated_at=now,
        )
    )
    mark_download(
        ledger,
        "mstc:1",
        ok=True,
        pdf_path="pdfs/1.pdf",
        content_changed=False,
        require_media_resync=False,
    )
    item = ledger.by_key()["mstc:1"]
    assert item.parse == "done"
    assert item.deploy_ready is True
    assert item.media_synced is True


def test_mark_download_content_changed_true_resets_parse_and_clears_sync():
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="done",
            deploy_ready=True,
            pdf_path="pdfs/1.pdf",
            media_synced=True,
            media_synced_at=now,
            first_queued_at=now,
            updated_at=now,
        )
    )
    mark_download(
        ledger,
        "mstc:1",
        ok=True,
        pdf_path="pdfs/1.pdf",
        content_changed=True,
        require_media_resync=True,
    )
    item = ledger.by_key()["mstc:1"]
    assert item.parse == "pending"
    assert item.deploy_ready is False
    assert item.media_synced is False
    assert item.media_synced_at is None


def test_mark_download_clears_pdf_path_on_failure():
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="pending",
            parse="pending",
            pdf_path="pdfs/1.pdf",
            first_queued_at=datetime.now(IST).isoformat(),
            updated_at=datetime.now(IST).isoformat(),
        )
    )
    mark_download(ledger, "mstc:1", ok=False, pdf_path=None, error="missing PDF")
    item = ledger.by_key()["mstc:1"]
    assert item.download == "failed"
    assert item.pdf_path is None
