from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.pipeline_build_deploy import reconcile_parse_marks_from_artifacts
from scraper.pipeline_ledger import LedgerItem, compute_publishable, empty_ledger

IST = ZoneInfo("Asia/Kolkata")


def test_reconcile_parse_marks_from_artifacts(tmp_path: Path):
    now = datetime.now(IST).isoformat()
    ledger = empty_ledger()
    ledger.items.append(
        LedgerItem(
            stable_key="mstc:42",
            source="mstc",
            source_auction_id="42",
            download="done",
            parse="pending",
            lots_count=0,
            hostinger_doc_path="pdfs/42.pdf",
            object_doc_url="https://cdn.example/pdfs/42.pdf",
            first_seen_at=now,
            updated_at=now,
        )
    )
    art_dir = tmp_path / "mstc"
    art_dir.mkdir(parents=True)
    (art_dir / "42.json").write_text(
        json.dumps(
            {
                "parser_version": "2",
                "record": {
                    "id": "42",
                    "source": "mstc",
                    "lots": [{"lot_no": "1", "description": "scrap"}],
                },
            }
        ),
        encoding="utf-8",
    )
    healed = reconcile_parse_marks_from_artifacts(ledger, tmp_path)
    assert healed == 1
    item = ledger.by_key()["mstc:42"]
    assert item.parse == "done"
    assert item.lots_count == 1
    assert compute_publishable(item)
