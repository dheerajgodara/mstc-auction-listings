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
            if key.endswith("/") or "/_poll/" in key or key.startswith("pdfs/_poll/"):
                continue
            if key.startswith("pdfs/_smoke/"):
                continue
            n += 1
            total += int(obj.get("Size") or 0)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return n, total


def publish_status(payload: str, *, wave_id: str | None = None, delta: int | None = None) -> None:
    """Write a tiny public status object so local curl can watch progress."""
    from scraper.object_store import upload_file
    import tempfile
    from pathlib import Path

    lines = [payload.rstrip("\n")]
    if wave_id is not None:
        lines.append(f"wave_id={wave_id}")
    if delta is not None:
        lines.append(f"delta={delta:+d}")
    body = "\n".join(lines) + "\n"

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "status.txt"
        path.write_text(body, encoding="utf-8")
        up = upload_file(path, key="pdfs/_poll/status.txt", content_type="text/plain")
        if not up.get("ok"):
            print(f"status upload warn: {up.get('error')}", flush=True)


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
    t_start = time.time()
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
        delta_n = 0 if prev_n is None else (n - prev_n)
        delta = "" if prev_n is None else f" delta={delta_n:+d}"
        rate = ""
        if prev_n is not None and args.interval > 0:
            rate = f" rate={delta_n / (args.interval / 60.0):.2f}/min"
        line = (
            f"[{_utc()}] poll={poll} pdfs_objects={n} bytes={nbytes}{delta}{rate} "
            f"list_ms={int(dt*1000)} elapsed_min={(time.time()-t_start)/60:.1f}"
        )
        print(line, flush=True)
        publish_status(line + "\n", delta=delta_n if prev_n is not None else None)
        if prev_n is not None and n > prev_n:
            print(
                f"[{_utc()}] NEW_UPLOADS +{n - prev_n} since last poll (~{args.interval:.0f}s window)",
                flush=True,
            )
        prev_n = n
        slept = time.time() - t0
        wait = max(0.0, args.interval - slept)
        if time.time() + wait >= deadline:
            break
        time.sleep(wait)

    print(f"[{_utc()}] R2 poll done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
