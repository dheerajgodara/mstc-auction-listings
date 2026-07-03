from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("scraper.notify")


def _webhook_url() -> str | None:
    url = (os.environ.get("NOTIFY_WEBHOOK_URL") or "").strip()
    return url or None


def send_failure_notification(
    *,
    summary: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 15,
) -> bool:
    """
    Optional failure webhook. Never raises — notification failures are logged only.
    Returns True when a notification was sent successfully.
    """
    url = _webhook_url()
    if not url:
        return False

    body = {
        "text": summary,
        "summary": summary,
        "payload": payload or {},
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "MSTC-Refresh-Notify/1.0"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status >= 400:
                logger.warning("notification webhook returned HTTP %s", resp.status)
                return False
        logger.info("failure notification sent")
        return True
    except urllib.error.URLError as exc:
        logger.warning("notification webhook failed: %s", exc)
        return False
    except Exception as exc:
        logger.warning("notification webhook error: %s", exc)
        return False
