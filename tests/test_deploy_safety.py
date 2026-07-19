from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.deploy import DeployValidationError, validate_deploy_export

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture(autouse=True)
def _clear_small_export_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests assert production gates; cutover env must not leak into them."""
    monkeypatch.delenv("PIPELINE_ALLOW_SMALL_EXPORT", raising=False)


def _record_dict(rid: str, *, source: str = "mstc") -> dict:
    return {
        "id": rid,
        "source": source,
        "source_auction_id": rid,
        "auction_number": rid,
        "region": "JPR",
        "office": "JPR",
        "closing": "2026-07-10T10:00:00+05:30",
        "lots": [{"lot_id": "1", "item_title": "Item"}],
    }


def _write_out_export(out_dir: Path, records: list[dict]) -> None:
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(IST).isoformat(),
        "count": len(records),
        "auctions": records,
    }
    (data_dir / "auctions.json").write_text(json.dumps(payload), encoding="utf-8")


def test_validate_deploy_export_accepts_full_multi_source(tmp_path: Path):
    records = [_record_dict(f"m{i}", source="mstc") for i in range(1681)]
    records.extend(_record_dict(f"ea-{i}", source="eauction") for i in range(61))
    records.extend(_record_dict(f"gem-{i}", source="gem_forward") for i in range(74))
    out_dir = tmp_path / "out"
    _write_out_export(out_dir, records)

    count, by_source = validate_deploy_export(out_dir)
    assert count == 1816
    assert by_source["mstc"] == 1681
    assert by_source["eauction"] == 61
    assert by_source["gem_forward"] == 74


def test_validate_deploy_export_rejects_capped_mstc_only(tmp_path: Path):
    out_dir = tmp_path / "out"
    _write_out_export(out_dir, [_record_dict(f"m{i}", source="mstc") for i in range(300)])

    with pytest.raises(DeployValidationError, match="Refusing to deploy capped MSTC-only export"):
        validate_deploy_export(out_dir)


def test_validate_deploy_export_rejects_one_record(tmp_path: Path):
    out_dir = tmp_path / "out"
    _write_out_export(out_dir, [_record_dict("1")])

    with pytest.raises(DeployValidationError, match="count is 1"):
        validate_deploy_export(out_dir)


def test_validate_deploy_export_allows_empty_under_cutover_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PIPELINE_ALLOW_SMALL_EXPORT", "1")
    out_dir = tmp_path / "out"
    _write_out_export(out_dir, [])

    count, by_source = validate_deploy_export(out_dir)
    assert count == 0
    assert by_source == {}


def test_validate_deploy_export_rejects_missing_data(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(DeployValidationError, match="missing deploy data file"):
        validate_deploy_export(out_dir)


def test_validate_deploy_export_rejects_unparseable_json(tmp_path: Path):
    out_dir = tmp_path / "out"
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "auctions.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(DeployValidationError, match="cannot parse"):
        validate_deploy_export(out_dir)
