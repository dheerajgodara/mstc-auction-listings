from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.pdf_flush import CataloguePdfFlushQueue, mark_pdfs_hostinger_synced
from scraper.pipeline_ledger import LedgerItem, empty_ledger
from scraper.raw_store import RawSyncResult, push_public_pdf_files


def test_push_public_pdf_files_empty_is_noop():
    result = push_public_pdf_files(public_dir=Path("/tmp"), filenames=[])
    assert result.ok is True
    assert result.attempted is False


def test_push_public_pdf_files_rsync_files_from(tmp_path: Path, monkeypatch):
    public = tmp_path / "public"
    pdfs = public / "pdfs"
    pdfs.mkdir(parents=True)
    (pdfs / "111.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)
    (pdfs / "222.pdf").write_bytes(b"%PDF-1.4\n" + b"y" * 2000)

    monkeypatch.setenv("HOSTINGER_HOST", "example.test")
    monkeypatch.setenv("HOSTINGER_PORT", "22")
    monkeypatch.setenv("HOSTINGER_USERNAME", "u")
    monkeypatch.setenv("HOSTINGER_REMOTE_DIR", "/remote/auctions")
    key = tmp_path / "key"
    key.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("HOSTINGER_SSH_KEY", str(key))

    with patch("scraper.raw_store.shutil.which", return_value="/usr/bin/rsync"):
        with patch("scraper.raw_store._ensure_remote_dir", return_value=None):
            with patch("scraper.raw_store._run_rsync_with_retries") as run:
                result = push_public_pdf_files(
                    public_dir=public,
                    filenames=["111.pdf", "pdfs/222.pdf", "111.pdf"],
                )

    assert result.ok is True
    assert result.attempted is True
    assert set(result.files) == {"111.pdf", "222.pdf"}
    assert run.called
    cmd = run.call_args.args[0] if run.call_args.args else run.call_args[0][0]
    assert "--chmod=F644" in cmd
    kwargs = run.call_args.kwargs
    assert "111.pdf" in (kwargs.get("input_text") or "")
    assert "222.pdf" in (kwargs.get("input_text") or "")


def test_flush_queue_marks_synced_and_flushes_every_n(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    public = tmp_path / "public"
    (public / "pdfs").mkdir(parents=True)
    ledger = empty_ledger()
    now = "2026-07-18T00:00:00+05:30"
    for aid in ("1", "2", "3"):
        ledger.items.append(
            LedgerItem(
                stable_key=f"mstc:{aid}",
                source="mstc",
                source_auction_id=aid,
                download="done",
                parse="pending",
                pdf_path=f"pdfs/{aid}.pdf",
                first_queued_at=now,
                updated_at=now,
            )
        )
        (public / "pdfs" / f"{aid}.pdf").write_bytes(b"%PDF-1.4\n" + b"z" * 2000)

    stats: dict = {}
    warnings: list[str] = []
    queue = CataloguePdfFlushQueue(
        public_dir=public,
        ledger=ledger,
        flush_every=2,
        stats=stats,
        warnings=warnings,
    )

    with patch(
        "scraper.pdf_flush.push_public_pdf_files",
        return_value=RawSyncResult(True, True, "ok", files=["1.pdf", "2.pdf"]),
    ) as push:
        queue.enqueue("1")
        assert ledger.by_key()["mstc:1"].media_synced is False
        assert queue.maybe_flush() is None  # need 2
        queue.enqueue("2")
        result = queue.maybe_flush()
        assert result is not None and result.ok
        push.assert_called_once()
        assert ledger.by_key()["mstc:1"].media_synced is True
        assert ledger.by_key()["mstc:2"].media_synced is True
        assert stats["pdf_hostinger_flushed"] == 2


def test_flush_queue_hard_fail_requeues(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    public = tmp_path / "public"
    (public / "pdfs").mkdir(parents=True)
    ledger = empty_ledger()
    now = "2026-07-18T00:00:00+05:30"
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:9",
            source="mstc",
            source_auction_id="9",
            download="done",
            parse="pending",
            pdf_path="pdfs/9.pdf",
            first_queued_at=now,
            updated_at=now,
        )
    )
    (public / "pdfs" / "9.pdf").write_bytes(b"%PDF-1.4\n" + b"z" * 2000)
    queue = CataloguePdfFlushQueue(
        public_dir=public,
        ledger=ledger,
        flush_every=1,
        stats={},
        warnings=[],
    )
    with patch(
        "scraper.pdf_flush.push_public_pdf_files",
        return_value=RawSyncResult(True, False, "boom"),
    ):
        queue.enqueue("9")
        try:
            queue.maybe_flush()
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "boom" in str(exc)
    assert raised
    assert queue.pending_count == 1
    assert ledger.by_key()["mstc:9"].media_synced is False


def test_mark_pdfs_hostinger_synced():
    ledger = empty_ledger()
    now = "2026-07-18T00:00:00+05:30"
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:5",
            source="mstc",
            source_auction_id="5",
            download="done",
            parse="pending",
            media_synced=False,
            first_queued_at=now,
            updated_at=now,
        )
    )
    n = mark_pdfs_hostinger_synced(ledger, ["5.pdf"], synced=True)
    assert n == 1
    assert ledger.by_key()["mstc:5"].media_synced is True
