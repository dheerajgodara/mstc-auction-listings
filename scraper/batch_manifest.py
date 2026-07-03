from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

BATCH_STATUS_PENDING = "pending"
BATCH_STATUS_RUNNING = "running"
BATCH_STATUS_DONE = "done"
BATCH_STATUS_FAILED = "failed"
BATCH_STATUS_SKIPPED = "skipped"


class BatchManifest:
    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self.path = path
        self.data = data

    @classmethod
    def load_or_create(cls, path: Path, *, min_closing_date: str | None = None) -> BatchManifest:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(path, data)
        now = datetime.now(IST).isoformat()
        data = {
            "created_at": now,
            "updated_at": now,
            "min_closing_date": min_closing_date,
            "batches": [],
            "docs_budget_remaining": None,
        }
        manifest = cls(path, data)
        manifest.save()
        return manifest

    def save(self) -> None:
        self.data["updated_at"] = datetime.now(IST).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        for batch in self.data.get("batches", []):
            if batch.get("batch_id") == batch_id:
                return batch
        return None

    def upsert_batch(self, entry: dict[str, Any]) -> None:
        batches = self.data.setdefault("batches", [])
        batch_id = entry["batch_id"]
        for i, batch in enumerate(batches):
            if batch.get("batch_id") == batch_id:
                batches[i] = {**batch, **entry}
                break
        else:
            batches.append(entry)
        self.save()

    def mark_running(self, batch_id: str, **fields: Any) -> None:
        now = datetime.now(IST).isoformat()
        existing = self.get_batch(batch_id) or {}
        self.upsert_batch(
            {
                "batch_id": batch_id,
                "status": BATCH_STATUS_RUNNING,
                "started_at": existing.get("started_at") or now,
                **fields,
            }
        )

    def mark_done(self, batch_id: str, **fields: Any) -> None:
        self.upsert_batch(
            {
                "batch_id": batch_id,
                "status": BATCH_STATUS_DONE,
                "finished_at": datetime.now(IST).isoformat(),
                **fields,
            }
        )

    def mark_failed(self, batch_id: str, error: str, **fields: Any) -> None:
        existing = self.get_batch(batch_id) or {}
        errors = list(existing.get("errors") or [])
        errors.append(error)
        self.upsert_batch(
            {
                "batch_id": batch_id,
                "status": BATCH_STATUS_FAILED,
                "finished_at": datetime.now(IST).isoformat(),
                "errors": errors,
                **fields,
            }
        )

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for batch in self.data.get("batches", []):
            status = batch.get("status", BATCH_STATUS_PENDING)
            counts[status] = counts.get(status, 0) + 1
        counts["total"] = len(self.data.get("batches", []))
        return counts

    def completed_batch_files(self, batch_dir: Path) -> list[Path]:
        files: list[Path] = []
        for batch in self.data.get("batches", []):
            if batch.get("status") != BATCH_STATUS_DONE:
                continue
            output_file = batch.get("output_file")
            if not output_file:
                continue
            path = batch_dir / output_file
            if path.is_file():
                files.append(path)
        return files
