"""Parse lane: Hostinger save/verify gate, pause, batch-end durability retry."""

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
        error="Hostinger parse artifact push/verify failed",
        durability_failed=True,
    )
    assert ledger.by_key()["mstc:1"].parse == "pending"


def test_push_fail_does_not_mark_done(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    (repo / "work" / "parsed").mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.append(_ready_item("10"))
    write_ledger(ledger, ledger_path)
    (public / "pdfs" / "10.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    sleep_calls: list[float] = []

    with patch("scraper.pipeline_parse_assets.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_parse_assets.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_parse_assets.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch(
                    "scraper.pipeline_parse_assets.DEFAULT_PARSED_DIR",
                    repo / "work" / "parsed",
                ):
                    with patch("scraper.pipeline_parse_assets.REPO_ROOT", repo):
                        with patch(
                            "scraper.pipeline_parse_assets.PARSE_SUCCESS_PAUSE_SEC", 5.0
                        ):
                            with patch(
                                "scraper.pipeline_parse_assets.PARSE_BATCH_RETRY_ROUNDS", 0
                            ):
                                with patch(
                                    "scraper.pipeline_parse_assets.pull_ledger",
                                    return_value=True,
                                ):
                                    with patch(
                                        "scraper.pipeline_parse_assets.push_ledger",
                                        return_value=True,
                                    ):
                                        with patch(
                                            "scraper.pipeline_parse_assets.pull_parsed_tree",
                                            return_value=0,
                                        ):
                                            with patch(
                                                "scraper.pipeline_parse_assets._hostinger_ssh_config",
                                                return_value={
                                                    "host": "h",
                                                    "port": "22",
                                                    "username": "u",
                                                    "key_path": "/k",
                                                    "remote_dir": "/r",
                                                },
                                            ):
                                                with patch(
                                                    "scraper.pipeline_parse_assets.pull_raw_files"
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_parse_assets.pull_public_pdf_files"
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_parse_assets._parse_record",
                                                            return_value={
                                                                "lots": [{"lot_id": "1"}],
                                                                "id": "10",
                                                            },
                                                        ):
                                                            with patch(
                                                                "scraper.pipeline_parse_assets.push_and_verify_parsed_file",
                                                                return_value=False,
                                                            ) as push_v:
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
                                                                            with patch(
                                                                                "scraper.pipeline_parse_assets.time.sleep",
                                                                                side_effect=lambda s: sleep_calls.append(
                                                                                    s
                                                                                ),
                                                                            ):
                                                                                result = run_parse_assets(
                                                                                    repo_root=repo,
                                                                                    max_parse=5,
                                                                                    batch_size=25,
                                                                                )

    assert push_v.called
    assert result["parsed"] == 0
    assert result["failed"] >= 1
    assert sleep_calls == [5.0]
    loaded = load_ledger(ledger_path)
    assert loaded.by_key()["mstc:10"].parse == "pending"


def test_batch_end_retries_durability_then_succeeds(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    parsed_root = repo / "work" / "parsed"
    parsed_root.mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    ledger.items.append(_ready_item("20"))
    write_ledger(ledger, ledger_path)
    (public / "pdfs" / "20.pdf").write_bytes(b"%PDF-1.4\n" + b"y" * 2000)

    push_calls = {"n": 0}

    def fake_push(local_path, *, source, source_auction_id):
        push_calls["n"] += 1
        return push_calls["n"] >= 2  # fail first, succeed on batch-end retry

    with patch("scraper.pipeline_parse_assets.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_parse_assets.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_parse_assets.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch("scraper.pipeline_parse_assets.DEFAULT_PARSED_DIR", parsed_root):
                    with patch("scraper.pipeline_parse_assets.REPO_ROOT", repo):
                        with patch(
                            "scraper.pipeline_parse_assets.PARSE_SUCCESS_PAUSE_SEC", 0.0
                        ):
                            with patch(
                                "scraper.pipeline_parse_assets.PARSE_BATCH_RETRY_ROUNDS", 2
                            ):
                                with patch(
                                    "scraper.pipeline_parse_assets.pull_ledger",
                                    return_value=True,
                                ):
                                    with patch(
                                        "scraper.pipeline_parse_assets.push_ledger",
                                        return_value=True,
                                    ):
                                        with patch(
                                            "scraper.pipeline_parse_assets.pull_parsed_tree",
                                            return_value=0,
                                        ):
                                            with patch(
                                                "scraper.pipeline_parse_assets._hostinger_ssh_config",
                                                return_value={
                                                    "host": "h",
                                                    "port": "22",
                                                    "username": "u",
                                                    "key_path": "/k",
                                                    "remote_dir": "/r",
                                                },
                                            ):
                                                with patch(
                                                    "scraper.pipeline_parse_assets.pull_raw_files"
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_parse_assets.pull_public_pdf_files"
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_parse_assets._parse_record",
                                                            return_value={
                                                                "lots": [{"lot_id": "1"}],
                                                                "id": "20",
                                                            },
                                                        ):
                                                            with patch(
                                                                "scraper.pipeline_parse_assets.push_and_verify_parsed_file",
                                                                side_effect=fake_push,
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
                                                                            with patch(
                                                                                "scraper.pipeline_parse_assets.time.sleep"
                                                                            ):
                                                                                result = run_parse_assets(
                                                                                    repo_root=repo,
                                                                                    max_parse=5,
                                                                                    batch_size=25,
                                                                                )

    assert push_calls["n"] == 2
    assert load_ledger(ledger_path).by_key()["mstc:20"].parse == "done"
    assert result["parsed"] + result["skipped"] == 1
    assert result["failed"] == 0


def test_fresh_skip_without_remote_verify_does_not_mark_done(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_PUSH_REQUIRED", "1")
    repo = tmp_path / "repo"
    public = repo / "web" / "public"
    (public / "pdfs").mkdir(parents=True)
    parsed_root = repo / "work" / "parsed" / "mstc"
    parsed_root.mkdir(parents=True)
    ledger_path = repo / "work" / "pipeline_ledger.json"
    ledger = empty_ledger()
    item = _ready_item("30")
    item.doc_sha256 = "aabb"
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
        parser_version="1",
    )
    write_parse_artifact(parsed_root / "30.json", artifact)

    push_calls = {"n": 0}

    def fake_push(*_a, **_k):
        push_calls["n"] += 1
        return False

    with patch("scraper.pipeline_parse_assets.DEFAULT_PIPELINE_LEDGER", ledger_path):
        with patch("scraper.pipeline_parse_assets.DEFAULT_PDF_DIR", public / "pdfs"):
            with patch("scraper.pipeline_parse_assets.DEFAULT_RAW_DIR", repo / "work" / "raw"):
                with patch(
                    "scraper.pipeline_parse_assets.DEFAULT_PARSED_DIR",
                    repo / "work" / "parsed",
                ):
                    with patch("scraper.pipeline_parse_assets.REPO_ROOT", repo):
                        with patch(
                            "scraper.pipeline_parse_assets.PARSE_SUCCESS_PAUSE_SEC", 0.0
                        ):
                            with patch(
                                "scraper.pipeline_parse_assets.PARSE_BATCH_RETRY_ROUNDS", 0
                            ):
                                with patch(
                                    "scraper.pipeline_parse_assets.PARSER_CACHE_VERSION", "1"
                                ):
                                    with patch(
                                        "scraper.pipeline_parse_assets.pull_ledger",
                                        return_value=True,
                                    ):
                                        with patch(
                                            "scraper.pipeline_parse_assets.push_ledger",
                                            return_value=True,
                                        ):
                                            with patch(
                                                "scraper.pipeline_parse_assets.pull_parsed_tree",
                                                return_value=0,
                                            ):
                                                with patch(
                                                    "scraper.pipeline_parse_assets._hostinger_ssh_config",
                                                    return_value={
                                                        "host": "h",
                                                        "port": "22",
                                                        "username": "u",
                                                        "key_path": "/k",
                                                        "remote_dir": "/r",
                                                    },
                                                ):
                                                    with patch(
                                                        "scraper.pipeline_parse_assets.pull_raw_files"
                                                    ):
                                                        with patch(
                                                            "scraper.pipeline_parse_assets.pull_public_pdf_files"
                                                        ):
                                                            with patch(
                                                                "scraper.pipeline_parse_assets.verify_parsed_file",
                                                                return_value=False,
                                                            ):
                                                                with patch(
                                                                    "scraper.pipeline_parse_assets.push_and_verify_parsed_file",
                                                                    side_effect=fake_push,
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
                                                                                with patch(
                                                                                    "scraper.pipeline_parse_assets.time.sleep"
                                                                                ):
                                                                                    result = run_parse_assets(
                                                                                        repo_root=repo,
                                                                                        max_parse=5,
                                                                                    )

    assert push_calls["n"] >= 1
    assert result["parsed"] == 0
    assert load_ledger(ledger_path).by_key()["mstc:30"].parse == "pending"
