from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from scraper.batch_manifest import BATCH_STATUS_DONE, BATCH_STATUS_FAILED, BatchManifest
from scraper.export_guard import ExportGuardError
from scraper.filters import make_run_id, tomorrow_min_closing_date
from scraper.refresh_lock import RefreshLockError, acquire_refresh_lock, release_refresh_lock
from scraper.refresh_reports import render_final_report_md, write_final_reports
from scraper.safety_gates import SafetyGateConfig, run_safety_gates
from scraper.status_report import build_status_report

IST = ZoneInfo("Asia/Kolkata")
REPO_ROOT = Path(__file__).resolve().parent.parent


def _record_dict(
    rid: str,
    *,
    source: str = "mstc",
    closing: str = "2026-07-10T10:00:00+05:30",
) -> dict:
    return {
        "id": rid,
        "source": source,
        "source_auction_id": rid,
        "auction_number": rid,
        "region": "JPR",
        "office": "JPR",
        "closing": closing,
        "lots": [{"lot_id": "1", "item_title": "Item"}],
    }


def _write_export(path: Path, records: list[dict], stats: dict | None = None) -> None:
    payload = {
        "generated_at": datetime.now(IST).isoformat(),
        "count": len(records),
        "auctions": records,
        "stats": stats or {"html_failures": 0, "pdf_failures": 0},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_tomorrow_ist_min_closing_date():
    now = datetime(2026, 7, 3, 15, 30, tzinfo=IST)
    assert tomorrow_min_closing_date(now) == "2026-07-04"
    assert make_run_id(now) == "20260703_153000_IST"


def test_lock_acquire_and_release(tmp_path: Path):
    lock_path = tmp_path / "refresh.lock"
    lock = acquire_refresh_lock(lock_path=lock_path, run_id="run_a", stale_minutes=10)
    assert lock.run_id == "run_a"
    with pytest.raises(RefreshLockError):
        acquire_refresh_lock(lock_path=lock_path, run_id="run_b", stale_minutes=10)
    release_refresh_lock(lock_path, run_id="run_a")
    lock2 = acquire_refresh_lock(lock_path=lock_path, run_id="run_b", stale_minutes=10)
    assert lock2.run_id == "run_b"


def test_stale_lock_requires_break_flag(tmp_path: Path, monkeypatch):
    lock_path = tmp_path / "refresh.lock"
    lock_path.write_text(
        json.dumps(
            {
                "run_id": "old",
                "pid": 999999,
                "started_at": datetime.now(IST).isoformat(),
                "host": "test",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scraper.refresh_lock._process_alive", lambda pid: False)
    with pytest.raises(RefreshLockError):
        acquire_refresh_lock(lock_path=lock_path, run_id="new", stale_minutes=10)
    lock = acquire_refresh_lock(
        lock_path=lock_path,
        run_id="new",
        stale_minutes=10,
        break_stale_lock=True,
    )
    assert lock.run_id == "new"


def test_safety_gate_rejects_one_record_candidate(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    production = tmp_path / "production.json"
    _write_export(candidate, [_record_dict("1")])
    _write_export(production, [_record_dict(f"x{i}") for i in range(1200)])

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=1000,
            min_closing_date="2026-07-04",
            production_json=production,
        ),
    )
    assert result.passed is False
    assert any("one-record" in e for e in result.errors)


def test_safety_gate_rejects_large_count_drop(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    production = tmp_path / "production.json"
    _write_export(candidate, [_record_dict(f"c{i}") for i in range(500)])
    _write_export(production, [_record_dict(f"p{i}") for i in range(1800)])

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=100,
            min_closing_date="2026-07-04",
            production_json=production,
            max_drop_pct=0.40,
        ),
    )
    assert result.passed is False
    assert any("dropped more than" in e for e in result.errors)


def test_safety_gate_accepts_normal_candidate(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    production = tmp_path / "production.json"
    records = [_record_dict(f"mstc-{i}", source="mstc") for i in range(1500)]
    records.append(_record_dict("ea-1", source="eauction"))
    records.append(_record_dict("gem-1", source="gem_forward"))
    _write_export(candidate, records)
    _write_export(production, [_record_dict(f"p{i}", source="mstc") for i in range(1400)])

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=1000,
            min_closing_date="2026-07-04",
            production_json=production,
        ),
    )
    assert result.passed is True


def test_safety_gate_rejects_failed_mstc_batches(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    production = tmp_path / "production.json"
    records = [_record_dict(f"mstc-{i}", source="mstc") for i in range(1200)]
    records.append(_record_dict("ea-1", source="eauction"))
    _write_export(candidate, records)
    _write_export(production, records)

    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    manifest = BatchManifest.load_or_create(batch_dir / "manifest.json", min_closing_date="2026-07-04")
    manifest.mark_failed("mstc_JPR", "boom", source="mstc", office="JPR", output_file="mstc_JPR.json")

    result = run_safety_gates(
        candidate,
        config=SafetyGateConfig(
            min_count=1000,
            min_closing_date="2026-07-04",
            production_json=production,
            allow_failed_batches=False,
        ),
        batch_dir=batch_dir,
    )
    assert result.passed is False
    assert any("failed MSTC" in e for e in result.errors)


def test_final_report_generation(tmp_path: Path):
    payload = {
        "run_id": "20260703_120000_IST",
        "status": "success",
        "total_auctions": 1816,
        "warnings": ["example"],
    }
    md_path, json_path = write_final_reports(reports_dir=tmp_path / "reports", payload=payload)
    assert md_path.is_file()
    assert json_path.is_file()
    md = md_path.read_text(encoding="utf-8")
    assert "20260703_120000_IST" in md
    assert render_final_report_md(payload)


def test_status_report_reads_latest_run(tmp_path: Path, monkeypatch):
    runs = tmp_path / "work" / "runs"
    runs.mkdir(parents=True)
    (runs / "latest.json").write_text(
        json.dumps({"run_id": "r1", "status": "success", "finished_at": "t"}),
        encoding="utf-8",
    )
    prod = tmp_path / "web/public/data/auctions.json"
    prod.parent.mkdir(parents=True)
    _write_export(
        prod,
        [_record_dict(f"m{i}", source="mstc") for i in range(5)],
    )
    report = build_status_report(repo_root=tmp_path, check_live=False)
    assert report["production"]["count"] == 5
    assert report["last_run"]["run_id"] == "r1"


@patch("scraper.refresh_and_deploy.batch_run")
@patch("scraper.refresh_and_deploy.merge_batches")
@patch("scraper.refresh_and_deploy.run_safety_gates")
@patch("scraper.refresh_and_deploy.promote_export")
@patch("scraper.refresh_and_deploy._run_subprocess")
def test_refresh_dry_run_no_deploy_when_gates_fail(
    mock_subprocess,
    mock_promote,
    mock_gates,
    mock_merge,
    mock_batch,
    tmp_path: Path,
):
    from scraper.models import AuctionsExport
    from scraper.refresh_and_deploy import RefreshConfig, run_refresh_and_deploy
    from scraper.safety_gates import SafetyGateResult

    repo = tmp_path
    (repo / "web" / "public" / "data").mkdir(parents=True)
    production = repo / "web/public/data/auctions.json"
    _write_export(production, [_record_dict(f"p{i}") for i in range(1500)])

    mock_batch.return_value = MagicMock(
        data={"batches": [], "docs_budget_remaining": 1000},
        summary=lambda: {"done": 1, "total": 1},
    )
    mock_merge.return_value = AuctionsExport(
        generated_at=datetime.now(IST),
        count=10,
        auctions=[],
        stats={"total_lots_in_export": 0, "by_source": {}},
    )
    mock_gates.return_value = SafetyGateResult(
        passed=False,
        errors=["simulated gate failure"],
        candidate_count=10,
        production_count=1500,
    )

    config = RefreshConfig(
        repo_root=repo,
        lock_path=Path("work/refresh.lock"),
        deploy=False,
        skip_build=True,
        force_min_closing_date="2026-07-04",
        max_docs_per_run=10,
    )
    result = run_refresh_and_deploy(config)
    assert result.status == "failed"
    mock_promote.assert_not_called()
    mock_subprocess.assert_not_called()
    assert (repo / "work" / "runs" / result.run_id / "reports" / "final_report.json").is_file()


@patch("scraper.refresh_and_deploy.batch_run")
@patch("scraper.refresh_and_deploy.merge_batches")
@patch("scraper.refresh_and_deploy.run_safety_gates")
@patch("scraper.refresh_and_deploy.promote_export")
@patch("scraper.refresh_and_deploy._run_subprocess")
def test_refresh_no_deploy_on_success_without_flag(
    mock_subprocess,
    mock_promote,
    mock_gates,
    mock_merge,
    mock_batch,
    tmp_path: Path,
):
    from scraper.models import AuctionRecord, AuctionsExport, LotRecord
    from scraper.refresh_and_deploy import RefreshConfig, run_refresh_and_deploy
    from scraper.safety_gates import SafetyGateResult

    repo = tmp_path
    (repo / "web" / "public" / "data").mkdir(parents=True)
    production = repo / "web/public/data/auctions.json"
    _write_export(production, [_record_dict(f"p{i}") for i in range(1500)])

    mock_batch.return_value = MagicMock(
        data={"batches": [], "docs_budget_remaining": 1000},
        summary=lambda: {"done": 1, "total": 1},
    )
    record = AuctionRecord(
        id="1",
        source="mstc",
        source_auction_id="1",
        auction_number="1",
        region="JPR",
        office="JPR",
        closing=datetime(2026, 7, 10, tzinfo=IST),
        lots=[LotRecord(lot_id="1", item_title="x")],
    )
    mock_merge.return_value = AuctionsExport(
        generated_at=datetime.now(IST),
        count=1500,
        auctions=[record],
        stats={"total_lots_in_export": 1, "by_source": {"mstc": 1500}},
    )
    mock_gates.return_value = SafetyGateResult(
        passed=True,
        qa_report={"passed": True, "total_auctions": 1500},
        candidate_count=1500,
        production_count=1500,
        by_source={"mstc": 1500},
    )
    mock_promote.return_value = repo / "work/backups/auctions_test.json"

    config = RefreshConfig(
        repo_root=repo,
        lock_path=Path("work/refresh.lock"),
        deploy=False,
        skip_build=True,
        force_min_closing_date="2026-07-04",
    )
    result = run_refresh_and_deploy(config)
    assert result.status == "success"
    mock_promote.assert_called_once()
    mock_subprocess.assert_not_called()
