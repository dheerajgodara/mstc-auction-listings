"""Tests for record-level DLQ: repair, quarantine, http_verify InvalidURL."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scraper.export_hygiene import (
    apply_quarantine_skips,
    classify_strict_errors,
    extract_record_keys_from_errors,
    is_record_recoverable,
    is_site_threatening,
    repair_absolute_asset_paths,
)
from scraper.http_verify import _http_status, _pick_sample_urls, verify_live_site
from scraper.pipeline_drain import run_pipeline_drain
from scraper.pipeline_ledger import empty_ledger, write_ledger
from scraper.qa_summary import run_strict_qa


def _row(aid: str, *, pdf_url: str = "pdfs/x.pdf", closing: str = "2026-07-20T10:00:00+05:30") -> dict:
    return {
        "id": aid,
        "source": "mstc",
        "source_auction_id": aid,
        "auction_number": aid,
        "closing": closing,
        "pdf_url": pdf_url,
        "lots": [{"lot_id": "1", "preview_images": []}],
        "status": "complete",
        "region": "HO",
        "office": "HO",
    }


def _export(rows: list[dict]) -> dict:
    return {
        "generated_at": "2026-07-16T12:00:00+05:30",
        "count": len(rows),
        "auctions": rows,
        "stats": {"by_source": {"mstc": len(rows)}},
    }


def test_repair_absolute_pdfs_then_qa_passes(tmp_path: Path):
    rows = [_row(str(i)) for i in range(15)]
    rows[0]["pdf_url"] = "/pdfs/591395.pdf"
    rows[1]["lots"][0]["preview_images"] = ["/thumbs/1/a.webp"]
    result = repair_absolute_asset_paths(_export(rows))
    assert result.export["auctions"][0]["pdf_url"] == "pdfs/591395.pdf"
    assert result.export["auctions"][1]["lots"][0]["preview_images"] == ["thumbs/1/a.webp"]
    assert len(result.repaired) >= 2
    path = tmp_path / "c.json"
    path.write_text(__import__("json").dumps(result.export), encoding="utf-8")
    report = run_strict_qa(path, min_count=10, min_closing_date="2026-07-17")
    assert report["passed"] is True


def test_classify_absolute_path_is_record_recoverable():
    classified = classify_strict_errors(
        ["record 591395 contains absolute path /pdfs/"]
    )
    assert classified.absolute_path
    assert is_record_recoverable(classified)
    assert not is_site_threatening(classified)
    keys = extract_record_keys_from_errors(classified)
    assert keys == ["mstc:591395"]


def test_count_floor_is_site_threatening():
    classified = classify_strict_errors(["count below floor: 900 < 1000"])
    assert is_site_threatening(classified)
    assert not is_record_recoverable(classified)


def test_quarantine_cannot_breach_min_count():
    export = _export([_row("1"), _row("2")])
    with pytest.raises(RuntimeError, match="min_count"):
        apply_quarantine_skips(export, {"mstc:1", "mstc:2"}, min_count=2)


def test_http_status_invalid_url_does_not_raise():
    status, body, note = _http_status(
        "https://example.com/auctions/thumbs/590770/ATL000006 26 27T/x.webp"
    )
    # May fail DNS or return None with note; must not raise.
    assert status is None or isinstance(status, int)
    if status is None:
        assert note


def test_pick_sample_prefers_urls_without_spaces(tmp_path: Path):
    data = _export(
        [
            {
                **_row("1"),
                "lots": [
                    {
                        "lot_id": "1",
                        "preview_images": ["thumbs/1/bad space.webp", "thumbs/1/clean.webp"],
                    }
                ],
            }
        ]
    )
    # Fake files so both exist.
    public = tmp_path / "public"
    (public / "thumbs" / "1").mkdir(parents=True)
    (public / "thumbs" / "1" / "bad space.webp").write_bytes(b"x")
    (public / "thumbs" / "1" / "clean.webp").write_bytes(b"x")
    (public / "pdfs").mkdir(parents=True)
    (public / "pdfs" / "x.pdf").write_bytes(b"%PDF")
    path = tmp_path / "a.json"
    path.write_text(__import__("json").dumps(data), encoding="utf-8")
    _pdf, thumb, _ = _pick_sample_urls(path, output_assets_dir=public)
    assert thumb == "thumbs/1/clean.webp"


def test_verify_live_site_invalid_thumb_is_warning(monkeypatch, tmp_path: Path):
    def fake_status(url: str, *, timeout: int = 60):
        if "thumbs" in url and " " in url:
            return None, b"", "invalid URL: control characters"
        if url.rstrip("/").endswith("/auctions") or url.endswith("/auctions/"):
            return 200, b"<html>count 10</html>", None
        if "auctions.json" in url:
            return 200, b"{}", None
        if "auctions-data.js" in url:
            return 200, b"window.__AUCTIONS_EXPORT__={}", None
        if "sitemap.xml" in url:
            return 200, b"<urlset></urlset>", None
        if "/mstc/" in url:
            return 200, b"<h1>ok</h1>", None
        if url.endswith(".pdf"):
            return 200, b"%PDF", None
        return 200, b"ok", None

    monkeypatch.setattr("scraper.http_verify._http_status", fake_status)
    monkeypatch.setattr(
        "scraper.http_verify._pick_sample_urls",
        lambda *a, **k: ("pdfs/1.pdf", "thumbs/x/bad name.webp", []),
    )
    result = verify_live_site(base_url="https://scrapauctionindia.com/auctions")
    assert result.passed is True
    assert any("invalid" in w.lower() or "skipped" in w.lower() for w in result.warnings)


def test_drain_continues_when_parse_succeeds_after_quarantine(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.pipeline_drain.REPO_ROOT", tmp_path)
    monkeypatch.setattr("scraper.pipeline_drain.DEFAULT_PIPELINE_LEDGER", tmp_path / "pipeline_ledger.json")
    monkeypatch.setattr("scraper.pipeline_drain.pull_ledger", lambda **kw: True)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from scraper.pipeline_ledger import LedgerItem

    IST = ZoneInfo("Asia/Kolkata")
    ledger = empty_ledger()
    now = datetime.now(IST).isoformat()
    for i in range(5):
        ledger.items.append(
            LedgerItem(
                stable_key=f"mstc:{i}",
                source="mstc",
                source_auction_id=str(i),
                download="done",
                parse="pending",
                hostinger_doc_path=f"pdfs/{i}.pdf",
                object_doc_url=f"https://files.csmg.in/pdfs/{i}.pdf",
                priority_score=10,
                first_queued_at=now,
                updated_at=now,
            )
        )
    ledger_path = tmp_path / "pipeline_ledger.json"
    write_ledger(ledger, ledger_path)

    def fake_parse(**kwargs):
        write_ledger(empty_ledger(), ledger_path)
        return {
            "status": "success",
            "selected_count": 5,
            "parse_ok": 5,
            "parse_failed": 0,
            "quarantined_keys": ["mstc:591395"],
            "repaired_absolute_paths": 1,
            "recoverable_parse_errors": 2,
        }

    out = run_pipeline_drain(
        repo_root=tmp_path,
        parse_fn=fake_parse,
        deploy_fn=lambda **kw: {"status": "success"},
        parse_retries=3,
        max_cycles=5,
    )
    assert out["status"] == "success"
    assert out["recoverable_parse_errors"] == 2
    assert out["cycles"][0]["parse"]["quarantined_keys"] == ["mstc:591395"]
