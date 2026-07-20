"""Small R2/CDN smoke test: upload a tiny object, verify via files.csmg.in, delete.

Usage:
  R2_* secrets in env, then:
  PYTHONPATH=. python -m scraper.r2_smoke_test
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from scraper.config import R2_BUCKET, R2_PUBLIC_BASE_URL
from scraper.object_store import (
    public_object_url,
    r2_configured,
    upload_file,
    verify_public_object_url,
)


def main() -> int:
    base = (R2_PUBLIC_BASE_URL or "").rstrip("/")
    print(f"CDN={base} bucket={R2_BUCKET or '(unset)'}")
    if not base:
        print("FAIL: R2_PUBLIC_BASE_URL missing")
        return 2

    # Always probe CDN reachability (no API keys required).
    robots = f"{base}/robots.txt"
    if not verify_public_object_url(robots):
        # robots may 404 on empty buckets; domain must still answer.
        import requests

        r = requests.get(robots, timeout=20, headers={"User-Agent": "MSTC-Smoke/1.0"})
        print(f"robots GET status={r.status_code}")
        if r.status_code not in (200, 404):
            print("FAIL: CDN domain not reachable")
            return 1
    else:
        print(f"OK verify {robots}")

    if not r2_configured():
        print("SKIP upload: R2 API keys not configured in this environment")
        print("SMOKE_HTTP_OK")
        return 0

    key = f"pdfs/_smoke/{int(time.time())}.txt"
    payload = f"mstc-r2-smoke {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "smoke.txt"
        path.write_text(payload, encoding="utf-8")
        up = upload_file(path, key=key, content_type="text/plain")
    if not up.get("ok"):
        print(f"FAIL upload: {up.get('error')}")
        return 1
    url = up.get("url") or public_object_url(key)
    print(f"uploaded {url}")
    # Brief settle for CDN
    time.sleep(1.5)
    if not verify_public_object_url(str(url)):
        print(f"FAIL verify after upload: {url}")
        return 1
    print(f"OK verified {url}")
    print("SMOKE_UPLOAD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
