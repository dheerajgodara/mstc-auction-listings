from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scraper.raw_store import push_public_pdf_files


def test_push_public_pdf_files_empty_is_noop():
    result = push_public_pdf_files(public_dir=Path("/tmp"), filenames=[])
    assert result.ok is True
    assert result.attempted is False


def test_push_public_pdf_files_rsync_files_from(tmp_path: Path, monkeypatch):
    public = tmp_path / "public"
    pdfs = public / "pdfs"
    pdfs.mkdir(parents=True)
    (pdfs / "111.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)
    (pdfs / "222.pdf").write_bytes(b"%PDF-1.4\n" + b"y" * 2000)

    monkeypatch.setenv("HOSTINGER_HOST", "example.test")
    monkeypatch.setenv("HOSTINGER_PORT", "22")
    monkeypatch.setenv("HOSTINGER_USERNAME", "u")
    monkeypatch.setenv("HOSTINGER_REMOTE_DIR", "/remote/auctions")
    key = tmp_path / "key"
    key.write_text("fake-key\n", encoding="utf-8")
    monkeypatch.setenv("HOSTINGER_SSH_KEY", str(key))

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return MagicMock(returncode=0)

    with patch("scraper.raw_store.shutil.which", return_value="/usr/bin/rsync"):
        with patch("scraper.raw_store.subprocess.run", side_effect=_fake_run):
            result = push_public_pdf_files(
                public_dir=public,
                filenames=["111.pdf", "pdfs/222.pdf", "111.pdf"],
            )

    assert result.ok is True
    assert result.attempted is True
    assert "--files-from=-" in captured["cmd"]
    assert captured["cmd"][-2].endswith("pdfs/")
    assert "111.pdf" in captured["input"]
    assert "222.pdf" in captured["input"]
