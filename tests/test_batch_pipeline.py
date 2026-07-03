from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.batch_manifest import BATCH_STATUS_DONE, BatchManifest
from scraper.export_guard import ExportGuardError, is_protected_export_path, validate_export_write
from scraper.filters import apply_future_filter, parse_min_closing_date
from scraper.merge_batches import merge_batches
from scraper.models import AuctionRecord, AuctionsExport, LotRecord
from scraper.promote_export import promote_export
from scraper.qa_summary import run_strict_qa

IST = ZoneInfo("Asia/Kolkata")
REPO_ROOT = Path(__file__).resolve().parent.parent


def _record(
    rid: str,
    *,
    source: str = "mstc",
    source_auction_id: str | None = None,
    closing: datetime | None = None,
) -> AuctionRecord:
    return AuctionRecord(
        id=rid,
        source=source,
        source_auction_id=source_auction_id or rid,
        auction_number=rid,
        region="JPR",
        office="JPR",
        closing=closing or datetime(2026, 7, 10, tzinfo=IST),
        lots=[LotRecord(lot_id="1", item_title="Item")],
    )


def _write_batch(path: Path, records: list[AuctionRecord], stats: dict | None = None) -> None:
    export = AuctionsExport(
        generated_at=datetime.now(IST),
        count=len(records),
        auctions=records,
        stats=stats or {},
    )
    path.write_text(json.dumps(export.model_dump(mode="json"), indent=2), encoding="utf-8")


def test_manifest_resume_skips_done(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest = BatchManifest.load_or_create(manifest_path, min_closing_date="2026-07-04")
    manifest.mark_done("mstc_JPR", source="mstc", office="JPR", output_file="mstc_JPR.json", auction_count=2)
    (tmp_path / "mstc_JPR.json").write_text("{}", encoding="utf-8")
    batch = manifest.get_batch("mstc_JPR")
    assert batch["status"] == BATCH_STATUS_DONE
    assert manifest.summary()["done"] == 1


def test_merge_dedupe_and_future_filter(tmp_path: Path):
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    _write_batch(batch_dir / "mstc_JPR.json", [_record("1"), _record("2")], {"documents": {"refs_found": 3}})
    _write_batch(
        batch_dir / "eauction_latest.json",
        [_record("eauction:1", source="eauction", source_auction_id="1"), _record("1")],
        {},
    )
    manifest = BatchManifest.load_or_create(batch_dir / "manifest.json", min_closing_date="2026-07-04")
    manifest.mark_done("mstc_JPR", source="mstc", office="JPR", output_file="mstc_JPR.json", auction_count=2)
    manifest.mark_done("eauction", source="eauction", output_file="eauction_latest.json", auction_count=2)

    out = tmp_path / "future.json"
    export = merge_batches(batch_dir=batch_dir, out_path=out, min_closing_date="2026-07-04")
    assert export.count == 3
    assert export.stats["duplicates_removed"] == 1
    assert export.stats["by_source"]["mstc"] == 2
    assert export.stats["by_source"]["eauction"] == 1


def test_apply_future_filter_excludes_before_min_date():
    records = [
        _record("past", closing=datetime(2026, 7, 3, 12, 0, tzinfo=IST)),
        _record("ok", closing=datetime(2026, 7, 4, 0, 0, tzinfo=IST)),
    ]
    kept, stats = apply_future_filter(records, parse_min_closing_date("2026-07-04"))
    assert len(kept) == 1
    assert kept[0].id == "ok"
    assert stats["excluded_past_closing"] == 1


def test_promote_guard_rejects_small_export(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    target = tmp_path / "target.json"
    _write_batch(candidate, [_record("1")])
    with pytest.raises(ExportGuardError):
        promote_export(
            candidate=candidate,
            target=target,
            min_count=1000,
            min_closing_date="2026-07-04",
            backup_dir=tmp_path / "backups",
        )


def test_promote_guard_accepts_valid_candidate(tmp_path: Path):
    candidate = tmp_path / "candidate.json"
    target = tmp_path / "target.json"
    records = [
        _record(f"mstc-{i}", source="mstc", source_auction_id=str(i))
        for i in range(1000)
    ]
    records.append(_record("ea-1", source="eauction", source_auction_id="ea-1"))
    _write_batch(candidate, records)
    promote_export(
        candidate=candidate,
        target=target,
        min_count=1000,
        min_closing_date="2026-07-04",
        backup_dir=tmp_path / "backups",
        require_sources=["mstc", "eauction"],
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["count"] == 1001


def test_protected_path_guard():
    protected = REPO_ROOT / "web/public/data/auctions.json"
    work = REPO_ROOT / "work/test_guard.json"
    assert is_protected_export_path(protected, repo_root=REPO_ROOT)
    assert not is_protected_export_path(work, repo_root=REPO_ROOT)
    with pytest.raises(ExportGuardError):
        validate_export_write(protected, 1, repo_root=REPO_ROOT)


def test_tests_do_not_target_production_paths():
    for rel in ("tests/test_run_all.py",):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert 'Path("web/public/data/auctions.json")' not in text
        assert 'Path("web/out/data/auctions.json")' not in text


def test_strict_qa_rejects_one_record(tmp_path: Path):
    candidate = tmp_path / "one.json"
    _write_batch(candidate, [_record("1", source="mstc")])
    qa = run_strict_qa(candidate, min_count=1000, min_closing_date="2026-07-04", require_sources=["mstc"])
    assert qa["passed"] is False
    assert any("one-record" in e for e in qa["strict_errors"])
