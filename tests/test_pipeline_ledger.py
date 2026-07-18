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
    # Done but no pdf_path → must requeue.
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
    # Done with path but corrupt on disk → requeue.
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
            priority_score=40,
            first_queued_at=now,
            updated_at=now,
        )
    )
    # Done with valid PDF → skip.
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
    assert keys == ["mstc:new", "mstc:missing", "mstc:corrupt"]
    assert estimated_download_runs_to_clear(ledger, cap=2, pdf_dir=pdf_dir) == 2


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
