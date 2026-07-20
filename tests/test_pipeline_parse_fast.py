"""Fast parse wave architecture: journal + flush + no-pause orchestrator smoke."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.parse_flush import flush_parsed_files
from scraper.parse_journal import ParseJournal
from scraper.pipeline_ledger import LedgerItem, empty_ledger, load_ledger, write_ledger
from scraper.pipeline_parse_assets import run_parse_assets


def test_parse_journal_append_and_success_keys(tmp_path: Path):
    j = ParseJournal(tmp_path / "j.jsonl")
    j.append({"stable_key": "mstc:1", "ok": True, "lots": 3})
    j.append({"stable_key": "mstc:2", "ok": False, "error": "no lots"})
    assert j.success_keys() == {"mstc:1"}


def test_flush_parsed_files_noop_when_empty():
    ok, msg = flush_parsed_files([], parsed_root=Path("/tmp"))
    assert ok
    assert "nothing" in msg


def test_wave_parse_marks_done_and_flushes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    monkeypatch.setenv("PARSE_WORKERS", "1")
    monkeypatch.setenv("PARSE_WAVE_SIZE", "10")

    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    parsed_root = repo / "work" / "parsed"
    parsed_root.mkdir(parents=True)
    (repo / "work" / "raw" / "mstc").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"

    pdf = public / "pdfs" / "99.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    now = "2026-07-20T00:00:00+05:30"
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:99",
            source="mstc",
            source_auction_id="99",
            download="done",
            parse="pending",
            hostinger_doc_path="pdfs/99.pdf",
            hostinger_doc_url="https://example.com/auctions/pdfs/99.pdf",
            portal_doc_url="https://example.com/portal.pdf",
            doc_sha256="abc",
            first_queued_at=now,
            updated_at=now,
        )
    )
    write_ledger(ledger, ledger_path)

    worker_result = {
        "stable_key": "mstc:99",
        "source": "mstc",
        "source_auction_id": "99",
        "ok": True,
        "lots_count": 2,
        "record": {"id": "99", "lots": [{"lot_id": "1"}, {"lot_id": "2"}], "source": "mstc"},
        "engine": "pymupdf",
        "error": None,
        "parse_ms": 12,
        "doc_sha256": "abc",
    }

    class FakeFuture:
        def result(self):
            return worker_result

    class FakePool:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, spec):
            return FakeFuture()

    with patch("scraper.pipeline_parse_assets.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_parse_assets.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_parse_assets.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch("scraper.pipeline_parse_assets.DEFAULT_PARSED_DIR", parsed_root):
                    with patch("scraper.pipeline_parse_assets.REPO_ROOT", repo):
                        with patch(
                            "scraper.pipeline_parse_assets.pull_ledger", return_value=True
                        ):
                            with patch(
                                "scraper.pipeline_parse_assets.push_ledger", return_value=True
                            ):
                                with patch(
                                    "scraper.pipeline_parse_assets._hostinger_ssh_config",
                                    return_value={
                                        "host": "h",
                                        "port": "22",
                                        "username": "u",
                                        "key_path": "/k",
                                        "remote_dir": "/r/public_html/auctions",
                                    },
                                ):
                                    with patch(
                                        "scraper.pipeline_parse_assets._prefetch_wave"
                                    ):
                                        with patch(
                                            "scraper.pipeline_parse_assets.ProcessPoolExecutor",
                                            FakePool,
                                        ):
                                            with patch(
                                                "scraper.pipeline_parse_assets.as_completed",
                                                lambda futs: list(futs.keys()),
                                            ):
                                                with patch(
                                                    "scraper.pipeline_parse_assets.flush_parsed_files",
                                                    return_value=(True, "flushed 1"),
                                                ) as flush:
                                                    with patch(
                                                        "scraper.pipeline_parse_assets.acquire_refresh_lock"
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_parse_assets.release_refresh_lock"
                                                        ):
                                                            with patch(
                                                                "scraper.pipeline_parse_assets.send_lane_report",
                                                                return_value=True,
                                                            ):
                                                                result = run_parse_assets(
                                                                    repo_root=repo,
                                                                    max_parse=5,
                                                                    wave_size=10,
                                                                )

    assert result["parsed"] == 1
    assert flush.called
    loaded = load_ledger(ledger_path)
    assert loaded.by_key()["mstc:99"].parse == "done"
    assert (parsed_root / "mstc" / "99.json").is_file()
