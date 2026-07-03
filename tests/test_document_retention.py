import json
from pathlib import Path

from scraper.document_retention import cleanup_stale_document_dirs, load_active_auction_ids


def test_dry_run_cleanup(tmp_path: Path):
    docs = tmp_path / "docs"
    thumbs = tmp_path / "thumbs"
    (docs / "keep").mkdir(parents=True)
    (docs / "stale").mkdir(parents=True)
    (thumbs / "keep").mkdir(parents=True)
    (thumbs / "stale").mkdir(parents=True)

    result = cleanup_stale_document_dirs(
        active_auction_ids={"keep"},
        docs_dir=docs,
        thumbs_dir=thumbs,
        dry_run=True,
    )
    assert result["removed_docs"] == 1
    assert result["removed_thumbs"] == 1
    assert (docs / "stale").is_dir()
    assert (thumbs / "stale").is_dir()


def test_apply_cleanup_only_removes_stale(tmp_path: Path):
    docs = tmp_path / "docs"
    thumbs = tmp_path / "thumbs"
    (docs / "keep").mkdir(parents=True)
    (docs / "stale").mkdir(parents=True)
    (thumbs / "keep").mkdir(parents=True)
    (thumbs / "stale").mkdir(parents=True)

    cleanup_stale_document_dirs(
        active_auction_ids={"keep"},
        docs_dir=docs,
        thumbs_dir=thumbs,
        dry_run=False,
    )
    assert (docs / "keep").is_dir()
    assert not (docs / "stale").exists()
    assert (thumbs / "keep").is_dir()
    assert not (thumbs / "stale").exists()


def test_load_active_auction_ids(tmp_path: Path):
    payload = {
        "auctions": [
            {"id": "587164", "source_auction_id": "587164"},
            {"id": "gem_forward:1", "source_auction_id": "1"},
        ]
    }
    json_path = tmp_path / "auctions.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    ids = load_active_auction_ids(json_path)
    assert "587164" in ids
    assert "1" in ids
    assert "gem_forward:1" in ids
