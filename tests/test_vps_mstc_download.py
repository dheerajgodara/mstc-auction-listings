"""Unit tests for VPS MSTC download helpers (no live MSTC)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.vps_mstc_download import (
    delete_local_pdfs,
    should_abort_fail_streak,
)


def test_health_gate_abort_threshold():
    assert should_abort_fail_streak(4, threshold=5) is False
    assert should_abort_fail_streak(5, threshold=5) is True
    assert should_abort_fail_streak(6, threshold=5) is True


def test_delete_local_pdfs_only_existing(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"%PDF-1.4")
    assert delete_local_pdfs([a, b, tmp_path / "missing.pdf"]) == 1
    assert not a.exists()
    assert not b.exists()


def test_cdn_already_ok_requires_pdf_magic():
    from scraper import vps_mstc_download as mod

    class FakeResp:
        status_code = 200
        content = b"%PDF-1.4 rest"

        def close(self):
            return None

    with patch("requests.get", return_value=FakeResp()):
        assert mod.cdn_already_ok("123") is True

    class HtmlResp:
        status_code = 200
        content = b"<html>error</html>"

        def close(self):
            return None

    with patch("requests.get", return_value=HtmlResp()):
        assert mod.cdn_already_ok("123") is False


def test_run_marks_cdn_hit_without_fetch(tmp_path: Path, monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger
    from scraper import vps_mstc_download as mod

    IST = ZoneInfo("Asia/Kolkata")
    closing = (datetime.now(IST) + timedelta(hours=48)).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:999001",
            source="mstc",
            source_auction_id="999001",
            portal_doc_url="https://example.com/x.pdf",
            download="pending",
            parse="pending",
            closing=closing,
            priority_score=10,
            first_queued_at=closing,
            updated_at=closing,
        )
    )
    ledger_path = tmp_path / "pipeline_ledger.json"
    write_ledger(ledger, ledger_path)

    monkeypatch.setattr(mod, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(mod, "SCRATCH_ROOT", tmp_path / "scratch")
    monkeypatch.setattr(mod, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(mod, "pull_ledger", lambda **kw: True)
    monkeypatch.setattr(mod, "push_ledger", lambda **kw: True)
    monkeypatch.setattr(mod, "cdn_already_ok", lambda aid: True)
    monkeypatch.setattr(mod, "send_lane_report", lambda *a, **k: True)
    monkeypatch.setattr(mod, "acquire_refresh_lock", lambda **kw: None)
    monkeypatch.setattr(mod, "release_refresh_lock", lambda *a, **k: None)

    fetch = MagicMock()
    monkeypatch.setattr(mod, "fetch_mstc_to_local", fetch)
    flush = MagicMock(return_value=(True, "noop", []))
    monkeypatch.setattr(mod, "flush_download_files", flush)

    out = mod.run_vps_mstc_download(max_download=5, gap_sec=0, concurrency=2)
    assert out["status"] == "success"
    assert out["skipped_cdn"] == 1
    assert out["downloaded"] == 1
    fetch.assert_not_called()
    from scraper.pipeline_ledger import load_ledger

    loaded = load_ledger(ledger_path)
    assert loaded.by_key()["mstc:999001"].download == "done"


def test_fail_streak_aborts_before_more_fetches(tmp_path: Path, monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger
    from scraper import vps_mstc_download as mod

    IST = ZoneInfo("Asia/Kolkata")
    closing = (datetime.now(IST) + timedelta(hours=48)).isoformat()
    ledger = empty_ledger()
    for i in range(8):
        ledger.items.append(
            LedgerItem(
                stable_key=f"mstc:{1000 + i}",
                source="mstc",
                source_auction_id=str(1000 + i),
                portal_doc_url="https://example.com/x.pdf",
                download="pending",
                parse="pending",
                closing=closing,
                priority_score=10,
                first_queued_at=closing,
                updated_at=closing,
            )
        )
    ledger_path = tmp_path / "pipeline_ledger.json"
    write_ledger(ledger, ledger_path)

    monkeypatch.setattr(mod, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(mod, "SCRATCH_ROOT", tmp_path / "scratch")
    monkeypatch.setattr(mod, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(mod, "pull_ledger", lambda **kw: True)
    monkeypatch.setattr(mod, "push_ledger", lambda **kw: True)
    monkeypatch.setattr(mod, "cdn_already_ok", lambda aid: False)
    monkeypatch.setattr(mod, "send_lane_report", lambda *a, **k: True)
    monkeypatch.setattr(mod, "acquire_refresh_lock", lambda **kw: None)
    monkeypatch.setattr(mod, "release_refresh_lock", lambda *a, **k: None)

    def boom(**kwargs):
        item = kwargs["item"]
        return {
            "stable_key": item.stable_key,
            "source": "mstc",
            "source_auction_id": item.source_auction_id,
            "ok": False,
            "error": "HTTP 500",
        }

    monkeypatch.setattr(mod, "fetch_mstc_to_local", boom)

    out = mod.run_vps_mstc_download(
        max_download=8, gap_sec=0, concurrency=1, fail_streak_abort=5
    )
    assert out["status"] == "aborted_health"
    assert out["failed"] >= 5
    assert out["failed"] < 8
