"""Ledger Hostinger SPOF: R2 mirror fallback + transport redispatch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.pipeline_ledger import (
    LAST_LEDGER_PULL,
    LedgerItem,
    empty_ledger,
    ledger_file_usable,
    load_ledger,
    pull_ledger,
    push_ledger,
    push_ledger_r2_mirror,
    write_ledger,
)


def _sample_ledger(tmp_path: Path) -> Path:
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:1",
            source="mstc",
            source_auction_id="1",
            download="done",
            parse="done",
            lots_count=2,
            hostinger_doc_path="pdfs/1.pdf",
            first_queued_at="2026-07-22T00:00:00+05:30",
            updated_at="2026-07-22T00:00:00+05:30",
        )
    )
    path = tmp_path / "pipeline_ledger.json"
    write_ledger(ledger, path)
    return path


def test_ledger_file_usable_rejects_empty(tmp_path: Path):
    p = tmp_path / "empty.json"
    p.write_text('{"generated_at":"x","items":[]}\n', encoding="utf-8")
    assert ledger_file_usable(p, max_age_hours=None) is False


def test_pull_ledger_falls_back_to_r2(tmp_path: Path, monkeypatch):
    local = tmp_path / "pipeline_ledger.json"
    mirror = _sample_ledger(tmp_path / "remote")
    # Pretend Hostinger is configured but rsync always fails.
    monkeypatch.setattr(
        "scraper.pipeline_ledger._hostinger_ssh_config",
        lambda: {
            "host": "h",
            "port": "22",
            "username": "u",
            "key_path": "/tmp/k",
            "remote_dir": "/remote/public_html/auctions",
        },
    )
    monkeypatch.setattr("scraper.pipeline_ledger.shutil.which", lambda _: "/usr/bin/rsync")

    def boom(*a, **k):
        raise RuntimeError("rsync exit 255")

    monkeypatch.setattr("scraper.hostinger_ssh.run_rsync_with_retries", boom)

    def fake_download(dest: Path):
        dest.write_bytes(mirror.read_bytes())
        return {"ok": True, "path": str(dest), "key": "pipeline/pipeline_ledger.json"}

    monkeypatch.setattr(
        "scraper.object_store.download_ledger_mirror",
        fake_download,
    )
    ok = pull_ledger(local_path=local, attempts=1, allow_local_cache=False)
    assert ok is True
    assert LAST_LEDGER_PULL["source"] == "r2"
    assert len(load_ledger(local).items) == 1


def test_pull_ledger_uses_local_cache_when_r2_missing(tmp_path: Path, monkeypatch):
    local = _sample_ledger(tmp_path)
    monkeypatch.setattr("scraper.pipeline_ledger._hostinger_ssh_config", lambda: None)
    monkeypatch.setattr(
        "scraper.object_store.download_ledger_mirror",
        lambda dest: {"ok": False, "error": "missing"},
    )
    ok = pull_ledger(local_path=local, attempts=1, allow_r2_fallback=True, allow_local_cache=True)
    assert ok is True
    assert LAST_LEDGER_PULL["source"] == "local_cache"


def test_push_ledger_mirrors_r2_even_without_ssh(tmp_path: Path, monkeypatch):
    local = _sample_ledger(tmp_path)
    monkeypatch.setattr("scraper.pipeline_ledger._hostinger_ssh_config", lambda: None)
    uploaded = {}

    def fake_upload(path: Path):
        uploaded["path"] = str(path)
        uploaded["bytes"] = path.stat().st_size
        return {"ok": True, "key": "pipeline/pipeline_ledger.json"}

    monkeypatch.setattr("scraper.object_store.upload_ledger_mirror", fake_upload)
    assert push_ledger(local_path=local) is True
    assert uploaded["path"] == str(local)


def test_push_ledger_r2_mirror_helper(tmp_path: Path, monkeypatch):
    local = _sample_ledger(tmp_path)
    calls = []

    monkeypatch.setattr(
        "scraper.object_store.upload_ledger_mirror",
        lambda path: calls.append(str(path)) or {"ok": True, "key": "pipeline/pipeline_ledger.json"},
    )
    assert push_ledger_r2_mirror(local) is True
    assert calls == [str(local)]


def test_pull_ledger_inner_rsync_attempts(tmp_path: Path, monkeypatch):
    local = tmp_path / "pipeline_ledger.json"
    monkeypatch.setattr(
        "scraper.pipeline_ledger._hostinger_ssh_config",
        lambda: {
            "host": "h",
            "port": "22",
            "username": "u",
            "key_path": "/tmp/k",
            "remote_dir": "/remote/public_html/auctions",
        },
    )
    monkeypatch.setattr("scraper.pipeline_ledger.shutil.which", lambda _: "/usr/bin/rsync")
    seen = {"attempts": None}

    def capture_rsync(cmd, *, timeout_sec, label, attempts=3):
        seen["attempts"] = attempts
        # Write a usable ledger so pull succeeds after rsync "works".
        ledger = empty_ledger()
        ledger.items.append(
            LedgerItem(
                stable_key="mstc:9",
                source="mstc",
                source_auction_id="9",
                download="done",
                parse="done",
                lots_count=1,
                hostinger_doc_path="pdfs/9.pdf",
                first_queued_at="2026-07-22T00:00:00+05:30",
                updated_at="2026-07-22T00:00:00+05:30",
            )
        )
        write_ledger(ledger, local)

    monkeypatch.setattr("scraper.hostinger_ssh.run_rsync_with_retries", capture_rsync)
    assert pull_ledger(local_path=local, attempts=1, allow_r2_fallback=False) is True
    assert seen["attempts"] == 3
    assert LAST_LEDGER_PULL["source"] == "hostinger"


def test_build_deploy_redispatches_once_on_empty_ledger(tmp_path: Path, monkeypatch):
    from scraper import pipeline_build_deploy as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "DEFAULT_PIPELINE_LEDGER", tmp_path / "work" / "pipeline_ledger.json")
    monkeypatch.setattr(mod, "DEFAULT_PARSED_DIR", tmp_path / "work" / "parsed")
    monkeypatch.setattr(mod, "DEFAULT_JSON_OUT", tmp_path / "web" / "public" / "data" / "auctions.json")
    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "web" / "public" / "data").mkdir(parents=True)

    monkeypatch.setattr(mod, "acquire_refresh_lock", lambda **k: None)
    monkeypatch.setattr(mod, "release_refresh_lock", lambda **k: None)
    monkeypatch.setattr(mod, "_recover_ledger", lambda p: False)
    monkeypatch.setattr(mod, "pull_parsed_tree", lambda **k: 0)
    monkeypatch.setattr(mod, "send_lane_report", lambda *a, **k: True)
    monkeypatch.setattr(mod, "pull_pipeline_json", lambda *a, **k: {})
    dispatched = {"n": 0}

    def fake_dispatch(wf, inputs=None):
        dispatched["n"] += 1
        dispatched["wf"] = wf
        return True

    monkeypatch.setattr(mod, "dispatch_workflow", fake_dispatch)
    monkeypatch.setattr(mod, "record_resume", lambda *a, **k: None)
    monkeypatch.setenv("BUILD_DEPLOY_SKIP_TRANSPORT_REDISPATCH", "0")
    # Ensure redispatch allowed
    monkeypatch.delenv("BUILD_DEPLOY_TRANSPORT_REDISPATCH", raising=False)

    try:
        mod.run_build_deploy(repo_root=tmp_path, break_stale_lock=True)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "R2 fallback" in str(exc) or "redispatched" in str(exc)
    assert dispatched["n"] == 1
    assert dispatched["wf"] == "pipeline-build-deploy.yml"
