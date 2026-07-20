"""Poll R2 pdfs/ object count every 40s; print deltas for live download visibility.

Usage (CI):
  PYTHONPATH=. python -m scraper.r2_poll_downloads --minutes 25 --interval 40
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from scraper.config import R2_BUCKET, R2_PUBLIC_BASE_URL
from scraper.object_store import _s3_client, r2_configured


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def count_pdf_objects() -> tuple[int, int]:
    """Return (object_count, total_bytes) under pdfs/ prefix."""
    client = _s3_client()
    token = None
    n = 0
    total = 0
    while True:
        kwargs = {"Bucket": R2_BUCKET, "Prefix": "pdfs/", "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = obj.get("Key") or ""
            if key.endswith("/"):
                continue
            n += 1
            total += int(obj.get("Size") or 0)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return n, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=25.0)
    parser.add_argument("--interval", type=float, default=40.0)
    args = parser.parse_args()

    print(f"[{_utc()}] R2 poll start bucket={R2_BUCKET} cdn={R2_PUBLIC_BASE_URL}", flush=True)
    if not r2_configured():
        print("FAIL: R2 not configured", flush=True)
        return 2

    deadline = time.time() + max(40.0, args.minutes * 60.0)
    prev_n = None
    poll = 0
    while time.time() < deadline:
        poll += 1
        t0 = time.time()
        try:
            n, nbytes = count_pdf_objects()
        except Exception as exc:
            print(f"[{_utc()}] poll={poll} ERROR {exc}", flush=True)
            time.sleep(args.interval)
            continue
        dt = time.time() - t0
        delta = "" if prev_n is None else f" delta={n - prev_n:+d}"
        rate = ""
        if prev_n is not None and args.interval > 0:
            rate = f" rate={(n - prev_n) / (args.interval / 60.0):.2f}/min"
        print(
            f"[{_utc()}] poll={poll} pdfs_objects={n} bytes={nbytes}{delta}{rate} list_ms={int(dt*1000)}",
            flush=True,
        )
        if prev_n is not None and n > prev_n:
            print(
                f"[{_utc()}] NEW_UPLOADS +{n - prev_n} since last poll (~{args.interval:.0f}s window)",
                flush=True,
            )
        prev_n = n
        # sleep remaining of interval
        slept = time.time() - t0
        wait = max(0.0, args.interval - slept)
        if time.time() + wait >= deadline:
            break
        time.sleep(wait)

    print(f"[{_utc()}] R2 poll done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
