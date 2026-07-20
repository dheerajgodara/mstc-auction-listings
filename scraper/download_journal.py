"""Append-only download journal for crash-safe wave processing + resume."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class DownloadJournal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")
        self._latest_fetch_ok: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        for row in self.read_all():
            key = str(row.get("stable_key") or "")
            if not key:
                continue
            if row.get("phase") == "fetch" and row.get("ok"):
                self._latest_fetch_ok[key] = row

    def append(self, event: dict[str, Any]) -> None:
        row = dict(event)
        row.setdefault("ts", datetime.now(IST).isoformat())
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        key = str(row.get("stable_key") or "")
        if key and row.get("phase") == "fetch" and row.get("ok"):
            self._latest_fetch_ok[key] = row

    def read_all(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.path.is_file():
            return rows
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    def latest_ok_fetch(self, stable_key: str) -> dict[str, Any] | None:
        return self._latest_fetch_ok.get(str(stable_key))

    def local_resume_path(self, stable_key: str) -> Path | None:
        row = self.latest_ok_fetch(stable_key)
        if not row:
            return None
        p = Path(str(row.get("local_path") or ""))
        if p.is_file():
            return p
        return None
