from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scraper.pipeline_drain import compute_max_cycles, parse_backlog_count, run_pipeline_drain
from scraper.pipeline_ledger import LedgerItem, empty_ledger, write_ledger
from scraper.download_retry_controller import decide_retry, slot_id_for

IST = ZoneInfo("Asia/Kolkata")


def _ledger_with_parse_pending(n: int, path):
    ledger = empty_ledger()
    now = datetime.now(IST).isoformat()
    for i in range(n):
        ledger.items.append(
            LedgerItem(
                stable_key=f"mstc:{i}",
                source="mstc",
                source_auction_id=str(i),
                download="done",
                parse="pending",
                priority_score=10,
                first_queued_at=now,
                updated_at=now,
            )
        )
    write_ledger(ledger, path)
    return ledger


def test_compute_max_cycles():
    assert compute_max_cycles(0) == 0
    assert compute_max_cycles(1) == 3
    assert compute_max_cycles(100) == 3
    assert compute_max_cycles(101) == 4
    assert compute_max_cycles(10000, hard_cap=25) == 25


def test_drain_empty_backlog(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.pipeline_drain.REPO_ROOT", tmp_path)
    monkeypatch.setattr("scraper.pipeline_drain.DEFAULT_PIPELINE_LEDGER", tmp_path / "pipeline_ledger.json")
    monkeypatch.setattr("scraper.pipeline_drain.pull_ledger", lambda **kw: False)
    monkeypatch.setattr("scraper.pipeline_drain.send_telegram_report", lambda *a, **k: True)
    write_ledger(empty_ledger(), tmp_path / "pipeline_ledger.json")

    calls = {"parse": 0, "deploy": 0}

    def fake_parse(**kwargs):
        calls["parse"] += 1
        return {"status": "success", "selected_count": 0}

    def fake_deploy(**kwargs):
        calls["deploy"] += 1
        return {"status": "success"}

    out = run_pipeline_drain(repo_root=tmp_path, parse_fn=fake_parse, deploy_fn=fake_deploy)
    assert out["status"] == "success"
    assert out["cycles_completed"] == 0
    assert calls["parse"] == 0
    assert calls["deploy"] == 0


def test_drain_parse_fail_stops_without_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_DRAIN_RETRY_SLEEP_SEC", "0")
    monkeypatch.setattr("scraper.pipeline_drain.REPO_ROOT", tmp_path)
    monkeypatch.setattr("scraper.pipeline_drain.DEFAULT_PIPELINE_LEDGER", tmp_path / "pipeline_ledger.json")
    monkeypatch.setattr("scraper.pipeline_drain.pull_ledger", lambda **kw: False)
    monkeypatch.setattr("scraper.pipeline_drain.send_telegram_report", lambda *a, **k: True)
    _ledger_with_parse_pending(5, tmp_path / "pipeline_ledger.json")

    calls = {"parse": 0, "deploy": 0}

    def fake_parse(**kwargs):
        calls["parse"] += 1
        raise RuntimeError("parse boom")

    def fake_deploy(**kwargs):
        calls["deploy"] += 1
        return {"status": "success"}

    with pytest.raises(RuntimeError, match="parse retries exhausted"):
        run_pipeline_drain(
            repo_root=tmp_path,
            parse_fn=fake_parse,
            deploy_fn=fake_deploy,
            parse_retries=3,
            max_cycles=5,
        )
    assert calls["parse"] == 3
    assert calls["deploy"] == 0


def test_drain_deploy_fail_stops_after_parse(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_DRAIN_RETRY_SLEEP_SEC", "0")
    monkeypatch.setattr("scraper.pipeline_drain.REPO_ROOT", tmp_path)
    monkeypatch.setattr("scraper.pipeline_drain.DEFAULT_PIPELINE_LEDGER", tmp_path / "pipeline_ledger.json")
    monkeypatch.setattr("scraper.pipeline_drain.pull_ledger", lambda **kw: False)
    monkeypatch.setattr("scraper.pipeline_drain.send_telegram_report", lambda *a, **k: True)
    _ledger_with_parse_pending(5, tmp_path / "pipeline_ledger.json")

    calls = {"parse": 0, "deploy": 0}

    def fake_parse(**kwargs):
        calls["parse"] += 1
        return {"status": "success", "selected_count": 5, "parse_ok": 5, "parse_failed": 0}

    def fake_deploy(**kwargs):
        calls["deploy"] += 1
        raise RuntimeError("deploy boom")

    with pytest.raises(RuntimeError, match="deploy retries exhausted"):
        run_pipeline_drain(
            repo_root=tmp_path,
            parse_fn=fake_parse,
            deploy_fn=fake_deploy,
            parse_retries=2,
            deploy_retries=3,
            max_cycles=5,
        )
    assert calls["parse"] == 1
    assert calls["deploy"] == 3


def test_drain_multi_cycle_until_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.pipeline_drain.REPO_ROOT", tmp_path)
    monkeypatch.setattr("scraper.pipeline_drain.DEFAULT_PIPELINE_LEDGER", tmp_path / "pipeline_ledger.json")
    monkeypatch.setattr("scraper.pipeline_drain.pull_ledger", lambda **kw: False)
    monkeypatch.setattr("scraper.pipeline_drain.send_telegram_report", lambda *a, **k: True)
    ledger_path = tmp_path / "pipeline_ledger.json"
    _ledger_with_parse_pending(3, ledger_path)

    state = {"parse_calls": 0}

    def fake_parse(**kwargs):
        state["parse_calls"] += 1
        # Clear backlog after first successful parse.
        write_ledger(empty_ledger(), ledger_path)
        return {"status": "success", "selected_count": 3, "parse_ok": 3, "parse_failed": 0}

    def fake_deploy(**kwargs):
        return {"status": "success", "deploy_skipped_unchanged": False}

    out = run_pipeline_drain(
        repo_root=tmp_path,
        parse_fn=fake_parse,
        deploy_fn=fake_deploy,
        max_cycles=5,
        max_parse=100,
    )
    assert out["status"] == "success"
    assert out["cycles_completed"] == 1
    assert state["parse_calls"] == 1


def test_drain_respects_max_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr("scraper.pipeline_drain.REPO_ROOT", tmp_path)
    monkeypatch.setattr("scraper.pipeline_drain.DEFAULT_PIPELINE_LEDGER", tmp_path / "pipeline_ledger.json")
    monkeypatch.setattr("scraper.pipeline_drain.pull_ledger", lambda **kw: False)
    monkeypatch.setattr("scraper.pipeline_drain.send_telegram_report", lambda *a, **k: True)
    ledger_path = tmp_path / "pipeline_ledger.json"
    _ledger_with_parse_pending(50, ledger_path)

    calls = {"n": 0}

    def fake_parse(**kwargs):
        calls["n"] += 1
        return {"status": "success", "selected_count": 100, "parse_ok": 100}

    def fake_deploy(**kwargs):
        return {"status": "success"}

    out = run_pipeline_drain(
        repo_root=tmp_path,
        parse_fn=fake_parse,
        deploy_fn=fake_deploy,
        max_cycles=2,
    )
    assert out["status"] == "success"
    assert out["cycles_completed"] == 2
    assert calls["n"] == 2


def test_decide_retry_budgets_per_slot():
    now = datetime(2026, 7, 15, 12, 30, tzinfo=IST)
    slot = slot_id_for(now)
    d1 = decide_retry(state={}, now=now, max_retries=2)
    assert d1.should_retry and d1.attempt == 1 and d1.wait_minutes == 15
    d2 = decide_retry(state={"slot_id": slot, "attempt": 1}, now=now, max_retries=2)
    assert d2.should_retry and d2.attempt == 2 and d2.wait_minutes == 45
    d3 = decide_retry(state={"slot_id": slot, "attempt": 2}, now=now, max_retries=2)
    assert not d3.should_retry
    # New slot resets
    later = datetime(2026, 7, 15, 18, 30, tzinfo=IST)
    d4 = decide_retry(state={"slot_id": slot, "attempt": 2}, now=later, max_retries=2)
    assert d4.should_retry and d4.attempt == 1
