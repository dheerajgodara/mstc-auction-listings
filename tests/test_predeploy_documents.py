"""Predeploy verify covers lot.documents missing files."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.predeploy_verify import verify_predeploy_build


def _write_minimal_out(out_dir: Path, auctions: list[dict]) -> None:
    (out_dir / "data").mkdir(parents=True)
    (out_dir / "pdfs").mkdir(parents=True)
    (out_dir / "docs").mkdir(parents=True)
    (out_dir / "thumbs").mkdir(parents=True)
    (out_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    payload = {
        "count": len(auctions),
        "auctions": auctions,
    }
    (out_dir / "data" / "auctions.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_predeploy_warns_on_missing_lot_docs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PREDEPLOY_DOCS_MODE", "warn")
    out = tmp_path / "out"
    # closing far in future
    auctions = [
        {
            "id": "589631",
            "source": "mstc",
            "closing": "2099-12-01T15:00:00+05:30",
            "pdf_url": "https://files.csmg.in/pdfs/589631.pdf",
            "object_doc_url": "https://files.csmg.in/pdfs/589631.pdf",
            "lots": [
                {
                    "lot_id": "1",
                    "documents": [
                        {
                            "type": "photo",
                            "filename": "Photo.pdf",
                            "cached_url": "docs/589631/Photo.pdf",
                            "thumbnail_url": "thumbs/589631/1/Photo.webp",
                            "status": "thumbnail_ready",
                        }
                    ]
                }
            ],
        }
    ]
    # Pad past min_count; include non-MSTC so capped-MSTC-only guard does not fire.
    for i in range(2, 12):
        auctions.append(
            {
                "id": str(i),
                "source": "mstc",
                "closing": "2099-12-01T15:00:00+05:30",
                "pdf_url": f"https://files.csmg.in/pdfs/{i}.pdf",
                "object_doc_url": f"https://files.csmg.in/pdfs/{i}.pdf",
                "lots": [{"lot_id": "1"}],
            }
        )
    auctions.append(
        {
            "id": "eauction-1",
            "source": "eauction",
            "closing": "2099-12-01T15:00:00+05:30",
            "pdf_url": "https://files.csmg.in/pdfs/eauction-1.pdf",
            "object_doc_url": "https://files.csmg.in/pdfs/eauction-1.pdf",
            "lots": [{"lot_id": "1"}],
        }
    )
    _write_minimal_out(out, auctions)
    result = verify_predeploy_build(
        out_dir=out,
        min_count=10,
        min_closing_date="2099-01-01",
        require_sources=["mstc"],
    )
    assert any("lot.documents" in w for w in result.warnings)
    assert result.passed  # warn mode


def test_predeploy_fails_on_missing_lot_docs_when_mode_fail(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PREDEPLOY_DOCS_MODE", "fail")
    out = tmp_path / "out"
    auctions = [
        {
            "id": "589631",
            "source": "mstc",
            "closing": "2099-12-01T15:00:00+05:30",
            "pdf_url": "https://files.csmg.in/pdfs/589631.pdf",
            "object_doc_url": "https://files.csmg.in/pdfs/589631.pdf",
            "lots": [
                {
                    "lot_id": "1",
                    "documents": [
                        {
                            "type": "photo",
                            "filename": "Photo.pdf",
                            "cached_url": "docs/589631/Photo.pdf",
                            "status": "downloaded",
                        }
                    ]
                }
            ],
        }
    ]
    for i in range(2, 12):
        auctions.append(
            {
                "id": str(i),
                "source": "mstc",
                "closing": "2099-12-01T15:00:00+05:30",
                "pdf_url": f"https://files.csmg.in/pdfs/{i}.pdf",
                "object_doc_url": f"https://files.csmg.in/pdfs/{i}.pdf",
                "lots": [{"lot_id": "1"}],
            }
        )
    auctions.append(
        {
            "id": "eauction-1",
            "source": "eauction",
            "closing": "2099-12-01T15:00:00+05:30",
            "pdf_url": "https://files.csmg.in/pdfs/eauction-1.pdf",
            "object_doc_url": "https://files.csmg.in/pdfs/eauction-1.pdf",
            "lots": [{"lot_id": "1"}],
        }
    )
    _write_minimal_out(out, auctions)
    result = verify_predeploy_build(
        out_dir=out,
        min_count=10,
        min_closing_date="2099-01-01",
        require_sources=["mstc"],
    )
    assert any("lot.documents" in e for e in result.errors)
    assert not result.passed
