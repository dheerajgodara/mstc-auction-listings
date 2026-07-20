"""Tests for Phase A/B download resilience (SSH helpers, fetched_local, journal)."""

from __future__ import annotations

from pathlib import Path

from scraper.download_journal import DownloadJournal
from scraper.hostinger_ssh import is_transport_error, rsync_timeout_args, ssh_base_opts, ssh_e
from scraper.object_store import r2_configured, upload_file
from scraper.pipeline_ledger import (
    LedgerItem,
    PipelineLedger,
    download_eligible,
    mark_download_fetched_local,
    publish_eligible,
    select_for_publish,
)


def test_ssh_base_opts_include_fail_fast() -> None:
    opts = ssh_base_opts(multiplex=False)
    blob = " ".join(opts)
    assert "ConnectTimeout=" in blob
    assert "ServerAliveInterval=" in blob
    assert "TCPKeepAlive=yes" in blob
    assert "ControlMaster" not in blob


def test_ssh_e_multiplex_uses_control_master() -> None:
    cfg = {
        "key_path": "/tmp/key",
        "port": "65002",
        "host": "h",
        "username": "u",
        "remote_dir": "/x",
    }
    s = ssh_e(cfg, multiplex=True, control_path="/tmp/mstc_dl_ssh_%C")
    assert "ControlMaster=auto" in s
    assert "ConnectTimeout=" in s


def test_rsync_timeout_args() -> None:
    assert rsync_timeout_args()[0].startswith("--timeout=")


def test_is_transport_error_exit_255() -> None:
    import subprocess

    exc = subprocess.CalledProcessError(255, ["ssh"])
    assert is_transport_error(exc) is True


def test_journal_resume_index(tmp_path: Path) -> None:
    local = tmp_path / "a.pdf"
    local.write_bytes(b"%PDF-1.4")
    j = DownloadJournal(tmp_path / "j.jsonl")
    j.append(
        {
            "stable_key": "mstc:1",
            "ok": True,
            "phase": "fetch",
            "local_path": str(local),
            "sha": "abc",
        }
    )
    j2 = DownloadJournal(tmp_path / "j.jsonl")
    assert j2.local_resume_path("mstc:1") == local
    assert j2.latest_ok_fetch("mstc:1")["sha"] == "abc"


def test_fetched_local_eligibility() -> None:
    item = LedgerItem(
        stable_key="mstc:1",
        source="mstc",
        source_auction_id="1",
        portal_doc_url="https://example/x",
        download="fetched_local",
        local_doc_path="/tmp/x.pdf",
    )
    assert download_eligible(item, source="mstc") is False
    assert publish_eligible(item, source="mstc") is True


def test_mark_download_fetched_local(tmp_path: Path) -> None:
    ledger = PipelineLedger(generated_at="t", items=[])
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:9",
            source="mstc",
            source_auction_id="9",
            portal_doc_url="https://example/x",
            download="pending",
        )
    )
    mark_download_fetched_local(
        ledger,
        "mstc:9",
        local_doc_path=str(tmp_path / "9.pdf"),
        hostinger_doc_path="pdfs/9.pdf",
    )
    got = ledger.by_key()["mstc:9"]
    assert got.download == "fetched_local"
    assert got.hostinger_doc_path == "pdfs/9.pdf"
    assert len(select_for_publish(ledger, limit=10)) == 1


def test_r2_not_configured_upload_fails_soft() -> None:
    assert r2_configured() is False
    out = upload_file(Path("/no/such"), key="pdfs/x.pdf")
    assert out["ok"] is False
