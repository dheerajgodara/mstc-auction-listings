"""Parse durability under fast wave architecture."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.parse_cache import build_parse_artifact, write_parse_artifact
from scraper.pipeline_ledger import LedgerItem, empty_ledger, load_ledger, mark_parse, write_ledger
from scraper.pipeline_parse_assets import run_parse_assets


def _ready_item(aid: str) -> LedgerItem:
    now = "2026-07-20T00:00:00+05:30"
    return LedgerItem(
        stable_key=f"mstc:{aid}",
        source="mstc",
        source_auction_id=aid,
        download="done",
        parse="pending",
        hostinger_doc_path=f"pdfs/{aid}.pdf",
        hostinger_doc_url=f"https://example.com/auctions/pdfs/{aid}.pdf",
        portal_doc_url="https://example.com/portal.pdf",
        doc_sha256="pdfhash",
        first_queued_at=now,
        updated_at=now,
    )


def test_mark_parse_durability_stays_pending():
    ledger = empty_ledger()
    ledger.items.append(_ready_item("1"))
    mark_parse(
        ledger,
        "mstc:1",
        ok=False,
        error="Hostinger parse flush failed",
        durability_failed=True,
    )
    assert ledger.by_key()["mstc:1"].parse == "pending"


def test_flush_fail_does_not_mark_done(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    monkeypatch.setenv("PARSE_WORKERS", "1")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    parsed_root = repo / "work" / "parsed"
    parsed_root.mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.append(_ready_item("10"))
    write_ledger(ledger, ledger_path)
    (public / "pdfs" / "10.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    worker_result = {
        "stable_key": "mstc:10",
        "source": "mstc",
        "source_auction_id": "10",
        "ok": True,
        "lots_count": 1,
        "record": {"id": "10", "lots": [{"lot_id": "1"}], "source": "mstc"},
        "engine": "pymupdf",
        "error": None,
        "parse_ms": 5,
        "doc_sha256": "pdfhash",
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
                                        "remote_dir": "/r/public_html/x",
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
                                                    return_value=(False, "rsync failed"),
                                                ):
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
                                                                try:
                                                                    run_parse_assets(
                                                                        repo_root=repo,
                                                                        max_parse=5,
                                                                    )
                                                                    raised = False
                                                                except RuntimeError:
                                                                    raised = True
    assert raised
    assert load_ledger(ledger_path).by_key()["mstc:10"].parse == "pending"


def test_fresh_skip_still_flushes_before_done(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    parsed_root = repo / "work" / "parsed" / "mstc"
    parsed_root.mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    item = _ready_item("30")
    ledger = empty_ledger()
    ledger.items.append(item)
    write_ledger(ledger, ledger_path)
    pdf = public / "pdfs" / "30.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"z" * 2000)
    from scraper.parse_cache import file_sha256

    pdf_hash = file_sha256(pdf)
    item.doc_sha256 = pdf_hash
    write_ledger(ledger, ledger_path)
    artifact = build_parse_artifact(
        record={"lots": [{"lot_id": "1"}], "id": "30"},
        stable_key="mstc:30",
        pdf_sha256=pdf_hash,
        parser_version="2",
    )
    write_parse_artifact(parsed_root / "30.json", artifact)

    with patch("scraper.pipeline_parse_assets.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_parse_assets.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_parse_assets.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch(
                    "scraper.pipeline_parse_assets.DEFAULT_PARSED_DIR",
                    repo / "work" / "parsed",
                ):
                    with patch("scraper.pipeline_parse_assets.REPO_ROOT", repo):
                        with patch(
                            "scraper.pipeline_parse_assets.PARSER_CACHE_VERSION", "2"
                        ):
                            with patch(
                                "scraper.pipeline_parse_assets.pull_ledger", return_value=True
                            ):
                                with patch(
                                    "scraper.pipeline_parse_assets.push_ledger",
                                    return_value=True,
                                ):
                                    with patch(
                                        "scraper.pipeline_parse_assets._hostinger_ssh_config",
                                        return_value={
                                            "host": "h",
                                            "port": "22",
                                            "username": "u",
                                            "key_path": "/k",
                                            "remote_dir": "/r/public_html/x",
                                        },
                                    ):
                                        with patch(
                                            "scraper.pipeline_parse_assets._prefetch_wave"
                                        ):
                                            with patch(
                                                "scraper.pipeline_parse_assets.flush_parsed_files",
                                                return_value=(False, "boom"),
                                            ):
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
                                                            try:
                                                                run_parse_assets(
                                                                    repo_root=repo,
                                                                    max_parse=5,
                                                                )
                                                                raised = False
                                                            except RuntimeError:
                                                                raised = True
    assert raised
    assert load_ledger(ledger_path).by_key()["mstc:30"].parse == "pending"
