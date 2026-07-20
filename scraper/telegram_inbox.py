"""Poll Telegram inbox for operator instructions (prefix: Deep).

Uses the same TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID as outbound reports.
Only messages from that chat whose text starts with \"Deep\" are treated as instructions.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scraper.telegram_reporter import send_ops_note

logger = logging.getLogger(__name__)

INSTRUCTION_PREFIX = "Deep"
DEFAULT_OFFSET_PATH = Path("work/telegram_inbox_offset.json")
DEFAULT_OUT_PATH = Path("work/telegram_inbox.json")


def _credentials() -> tuple[str, str] | None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return None
    return token, chat_id


def _api(token: str, method: str, params: dict[str, Any] | None = None, *, timeout: int = 30) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {payload}")
    return payload


def _load_offset(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("offset") or 0)
    except Exception:
        return 0


def _save_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"offset": offset}, indent=2) + "\n", encoding="utf-8")


def poll_inbox(
    *,
    offset_path: Path = DEFAULT_OFFSET_PATH,
    out_path: Path = DEFAULT_OUT_PATH,
    acknowledge: bool = True,
    ack_telegram: bool = True,
) -> dict[str, Any]:
    creds = _credentials()
    if not creds:
        result = {
            "ok": False,
            "error": "missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
            "instructions": [],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    token, chat_id = creds
    offset = _load_offset(offset_path)
    params: dict[str, Any] = {
        "timeout": 0,
        "allowed_updates": json.dumps(["message"]),
    }
    if offset > 0:
        params["offset"] = offset

    payload = _api(token, "getUpdates", params)
    updates = payload.get("result") or []

    instructions: list[dict[str, Any]] = []
    max_update_id = offset - 1 if offset else 0

    for upd in updates:
        update_id = int(upd.get("update_id") or 0)
        if update_id > max_update_id:
            max_update_id = update_id
        msg = upd.get("message") or {}
        from_chat = str((msg.get("chat") or {}).get("id") or "")
        if from_chat != str(chat_id):
            continue
        text = (msg.get("text") or "").strip()
        if not text.startswith(INSTRUCTION_PREFIX):
            continue
        instructions.append(
            {
                "update_id": update_id,
                "message_id": msg.get("message_id"),
                "date": msg.get("date"),
                "text": text,
                "instruction": text[len(INSTRUCTION_PREFIX) :].lstrip(" :-\t"),
            }
        )

    if acknowledge and max_update_id >= 0 and updates:
        # Confirm consumption so Telegram won't redeliver these updates.
        _save_offset(offset_path, max_update_id + 1)

    result = {
        "ok": True,
        "chat_id": chat_id,
        "offset_before": offset,
        "offset_after": _load_offset(offset_path) if acknowledge else offset,
        "updates_seen": len(updates),
        "instructions": instructions,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if ack_telegram and instructions:
        bullets = []
        for item in instructions:
            preview = item["text"]
            if len(preview) > 120:
                preview = preview[:117] + "…"
            bullets.append(preview)
        send_ops_note(
            "Deep instructions received",
            "Acting on next poll wake",
            bullets=bullets,
        )

    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Poll Telegram for Deep* instructions")
    parser.add_argument("--offset-path", type=Path, default=DEFAULT_OFFSET_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--no-ack", action="store_true", help="Do not advance offset")
    parser.add_argument("--no-telegram-ack", action="store_true", help="Do not send receipt message")
    args = parser.parse_args(argv)
    try:
        result = poll_inbox(
            offset_path=args.offset_path,
            out_path=args.out,
            acknowledge=not args.no_ack,
            ack_telegram=not args.no_telegram_ack,
        )
    except (urllib.error.URLError, RuntimeError, OSError) as exc:
        logger.error("inbox poll failed: %s", exc)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
