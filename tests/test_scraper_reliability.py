"""Reliability cleanup: discovery gate, asset sanitize, subprocess errors, AI fail-closed."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.finalize_public_export import (
    finalize_public_export,
    remove_missing_local_asset_links,
)
from scraper.incremental_plan import WorkPlanItem, build_work_plan
from scraper.incremental_queue import priority_score
from scraper.refresh_and_deploy import (
    SubprocessStepError,
    _assert_discovery_completeness,
    _run_subprocess,
)
from scraper.source_fallback import apply_missing_source_fallback, source_counts

IST = ZoneInfo("Asia/Kolkata")


def _auction(aid: str, source: str = "mstc", closing: str = "2030-07-12T10:00:00+05:30", **extra) -> dict:
    base = {
        "id": aid,
        "source": source,
        "source_auction_id": aid,
        "auction_number": aid,
        "region": "JPR",
        "office": "JPR",
        "closing": closing,
        "lots": [{"lot_id": "1", "item_title": "Item", "preview_images": []}],
    }
    base.update(extra)
    return base


def test_discovery_gate_aborts_when_mstc_zero_after_fallback():
    discovery = {
        "count": 2,
        "auctions": [_auction("g1", "gem_forward"), _auction("e1", "eauction")],
        "stats": {"by_source": {"gem_forward": 1, "eauction": 1}},
    }
    previous = {
        "count": 100,
        "auctions": [_auction(f"m{i}") for i in range(50)] + [_auction("g0", "gem_forward")],
    }
    with pytest.raises(RuntimeError, match="MSTC count is 0"):
        _assert_discovery_completeness(
            sources=["mstc", "gem_forward", "eauction"],
            discovery_data=discovery,
            previous_export=previous,
            allow_large_drop=False,
        )


def test_discovery_gate_aborts_on_large_total_drop():
    discovery = {"count": 100, "auctions": [_auction(f"m{i}") for i in range(100)]}
    previous = {"count": 2000, "auctions": [_auction(f"m{i}") for i in range(2000)]}
    with pytest.raises(RuntimeError, match="dropped"):
        _assert_discovery_completeness(
            sources=["mstc"],
            discovery_data=discovery,
            previous_export=previous,
            allow_large_drop=False,
        )


def test_fallback_restores_mstc_then_gate_passes_and_work_plan_keeps_mstc():
    candidate = {
        "generated_at": "2026-07-11T06:00:00+05:30",
        "count": 2,
        "auctions": [_auction("g1", "gem_forward"), _auction("e1", "eauction")],
        "stats": {
            "by_source": {"gem_forward": 1, "eauction": 1},
            "source_stats": {
                "mstc": {"complete": True, "source": "mstc"},
                "gem_forward": {"complete": True},
                "eauction": {"complete": True},
            },
        },
    }
    previous = {
        "generated_at": "2026-07-10T06:00:00+05:30",
        "count": 5,
        "auctions": [
            _auction("m1"),
            _auction("m2"),
            _auction("m3"),
            _auction("g0", "gem_forward"),
            _auction("e0", "eauction"),
        ],
    }
    out, report = apply_missing_source_fallback(
        candidate,
        previous_export=previous,
        min_closing_date="2026-07-11",
        fallback_sources=["mstc", "gem_forward", "eauction"],
    )
    assert report["applied"] is True
    assert source_counts(out)["mstc"] == 3
    _assert_discovery_completeness(
        sources=["mstc", "gem_forward", "eauction"],
        discovery_data=out,
        previous_export=previous,
        allow_large_drop=False,
    )
    plan = build_work_plan(out, previous)
    assert plan.by_source.get("mstc", {}).get("mark_removed", 0) == 0
    assert plan.by_source.get("mstc", {}).get("reuse_previous", 0) == 3


def test_remove_missing_local_asset_links_strips_pdfs_docs_thumbs(tmp_path: Path):
    public = tmp_path / "public"
    (public / "pdfs").mkdir(parents=True)
    (public / "docs").mkdir()
    (public / "thumbs" / "a").mkdir(parents=True)
    (public / "pdfs" / "ok.pdf").write_bytes(b"%PDF")
    (public / "docs" / "ok.doc").write_bytes(b"doc")
    (public / "thumbs" / "a" / "1.webp").write_bytes(b"img")

    export = {
        "count": 1,
        "auctions": [
            _auction(
                "x",
                pdf_url="pdfs/missing.pdf",
                document_urls=["pdfs/missing.pdf", "docs/missing.doc", "docs/ok.doc", "https://example.com/x.pdf"],
                lots=[
                    {
                        "lot_id": "1",
                        "item_title": "Item",
                        "preview_images": ["thumbs/a/1.webp", "thumbs/a/missing.webp"],
                    }
                ],
            )
        ],
    }
    removed = remove_missing_local_asset_links(export, public_dir=public)
    auction = export["auctions"][0]
    assert auction["pdf_url"] is None
    assert auction["document_urls"] == ["docs/ok.doc", "https://example.com/x.pdf"]
    assert auction["lots"][0]["preview_images"] == ["thumbs/a/1.webp"]
    assert removed["pdfs"] >= 1
    assert removed["docs"] == 1
    assert removed["thumbs"] == 1


def test_finalize_public_export_strips_all_missing_assets(tmp_path: Path):
    public = tmp_path / "public"
    data = public / "data"
    data.mkdir(parents=True)
    (public / "pdfs").mkdir()
    json_path = data / "auctions.json"
    history = data / "import-history.json"
    payload = {
        "generated_at": datetime(2026, 7, 4, 10, 0, tzinfo=IST).isoformat(),
        "count": 1,
        "auctions": [
            {
                **_auction("missing"),
                "pdf_url": "pdfs/nope.pdf",
                "document_urls": ["docs/nope.pdf"],
                "lots": [{"lot_id": "1", "item_title": "Item", "preview_images": ["thumbs/x.webp"]}],
            }
        ],
        "stats": {},
    }
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    out = finalize_public_export(
        json_path=json_path,
        history_path=history,
        automation_ran_at=datetime(2026, 7, 4, 11, 0, tzinfo=IST),
        run_id="test_run",
    )
    auction = out["auctions"][0]
    assert auction["pdf_url"] is None
    assert auction["document_urls"] == []
    assert auction["lots"][0]["preview_images"] == []
    assert out["stats"]["missing_local_asset_links_removed"] >= 2


def test_run_subprocess_attaches_tails_on_failure(tmp_path: Path):
    script = tmp_path / "fail.py"
    script.write_text("import sys\nprint('out')\nprint('err', file=sys.stderr)\nsys.exit(7)\n", encoding="utf-8")
    with pytest.raises(SubprocessStepError) as excinfo:
        _run_subprocess(["python3", str(script)], cwd=tmp_path, step="verify-build")
    err = excinfo.value
    assert err.returncode == 7
    assert err.step == "verify-build"
    assert "err" in (err.output.get("stderr_tail") or "")
    assert "out" in (err.output.get("stdout_tail") or "")


def test_deploy_rsync_protects_asset_dirs():
    from scraper import deploy as deploy_mod

    source = Path(deploy_mod.__file__).read_text(encoding="utf-8")
    assert "--filter=P pdfs/" in source
    assert "--filter=P docs/" in source
    assert "--filter=P thumbs/" in source


def test_non_mstc_batch_failure_is_soft_warning_not_hard_fail():
    """Documented contract: only MSTC batch failures abort refresh."""
    from scraper.refresh_and_deploy import _classify_failed_batches

    groups = _classify_failed_batches(
        {
            "batches": [
                {"batch_id": "gem_forward_latest", "source": "gem_forward", "status": "failed"},
                {"batch_id": "eauction_latest", "source": "eauction", "status": "failed"},
            ]
        }
    )
    assert groups["mstc"] == []
    assert "gem_forward_latest" in groups["non_mstc"]
    # Soft-fail path in run_refresh_and_deploy only raises when groups["mstc"] is non-empty.
    assert not groups["mstc"]


def test_priority_boosts_missing_local_assets(tmp_path: Path):
    public = tmp_path / "public"
    (public / "pdfs").mkdir(parents=True)
    item = WorkPlanItem(
        stable_key="mstc:1",
        source="mstc",
        source_auction_id="1",
        decision="needs_repair",
        action="deep_parse",
        reasons=["status_listing_only"],
        metadata={"closing": "2030-07-12T10:00:00+05:30"},
    )
    prev = _auction("1", pdf_url="pdfs/missing.pdf")
    boosted = priority_score(item, now=datetime(2026, 7, 11, tzinfo=IST), previous_record=prev, public_dir=public)
    plain = priority_score(item, now=datetime(2026, 7, 11, tzinfo=IST), previous_record=None, public_dir=None)
    assert boosted > plain


def test_cli_allow_network_without_key_fails_closed(tmp_path: Path, monkeypatch):
    from scraper.ai_enrichment import cli as ai_cli

    monkeypatch.setattr("scraper.config.OPENROUTER_API_KEY", "")
    monkeypatch.setattr(ai_cli, "count_cache_stats", lambda *_a, **_k: {"ready": 0, "failed": 0, "rejected": 0, "total": 0})
    json_path = tmp_path / "auctions.json"
    json_path.write_text(json.dumps({"count": 0, "auctions": []}), encoding="utf-8")
    code = ai_cli.main(
        [
            "--json",
            str(json_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "enrich",
            "--allow-network",
            "--limit",
            "1",
        ]
    )
    assert code == 2


def test_cli_refuses_hostinger_ledger_in_mock_mode(tmp_path: Path, monkeypatch):
    from scraper.ai_enrichment import cli as ai_cli

    monkeypatch.setattr("scraper.config.OPENROUTER_API_KEY", "")
    monkeypatch.setattr(ai_cli, "count_cache_stats", lambda *_a, **_k: {"ready": 0, "failed": 0, "rejected": 0, "total": 0})
    json_path = tmp_path / "auctions.json"
    json_path.write_text(json.dumps({"count": 0, "auctions": []}), encoding="utf-8")
    code = ai_cli.main(
        [
            "--json",
            str(json_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "enrich",
            "--mock",
            "--ledger-sync",
            "hostinger",
            "--limit",
            "1",
        ]
    )
    assert code == 2
