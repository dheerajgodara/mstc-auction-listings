"""QA summary accepts CDN absolute media URLs."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.qa_summary import run_strict_qa


def test_strict_qa_allows_cdn_pdf_urls(tmp_path: Path):
    auctions = [
        {
            "id": "1",
            "source": "mstc",
            "closing": "2099-12-01T15:00:00+05:30",
            "pdf_url": "https://files.csmg.in/pdfs/1.pdf",
            "object_doc_url": "https://files.csmg.in/pdfs/1.pdf",
            "lots": [
                {
                    "documents": [
                        {
                            "cached_url": "https://files.csmg.in/docs/1/a.pdf",
                            "thumbnail_url": "https://files.csmg.in/thumbs/1/a.webp",
                        }
                    ],
                    "preview_images": ["https://files.csmg.in/thumbs/1/a.webp"],
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
                "lots": [{"lot_id": "1"}],
            }
        )
    path = tmp_path / "auctions.json"
    path.write_text(json.dumps({"count": len(auctions), "auctions": auctions}), encoding="utf-8")
    report = run_strict_qa(path, min_count=10, min_closing_date="2099-01-01")
    assert report["passed"]
    assert not any("absolute path" in e for e in report.get("strict_errors") or [])


def test_strict_qa_still_rejects_site_root_paths(tmp_path: Path):
    auctions = [
        {
            "id": "591395",
            "source": "mstc",
            "closing": "2099-12-01T15:00:00+05:30",
            "pdf_url": "/pdfs/591395.pdf",
            "lots": [],
        }
    ]
    for i in range(2, 12):
        auctions.append(
            {
                "id": str(i),
                "source": "mstc",
                "closing": "2099-12-01T15:00:00+05:30",
                "pdf_url": f"https://files.csmg.in/pdfs/{i}.pdf",
                "lots": [],
            }
        )
    path = tmp_path / "auctions.json"
    path.write_text(json.dumps({"count": len(auctions), "auctions": auctions}), encoding="utf-8")
    report = run_strict_qa(path, min_count=10, min_closing_date="2099-01-01")
    assert not report["passed"]
    assert any("591395" in e and "absolute path" in e for e in report.get("strict_errors") or [])
