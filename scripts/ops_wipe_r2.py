#!/usr/bin/env python3
"""Fresh-start R2 wipe: delete all objects under pdfs/, docs/, thumbs/, pipeline/.

Requires R2_* env (same as object_store). Gated by CONFIRM=WIPE-PRODUCTION.
"""

from __future__ import annotations

import os
import sys

PREFIXES = ("pdfs/", "docs/", "thumbs/", "pipeline/")


def main() -> int:
    if (os.environ.get("CONFIRM") or "").strip() != "WIPE-PRODUCTION":
        print("Refusing: set CONFIRM=WIPE-PRODUCTION", file=sys.stderr)
        return 2

    # Ensure repo imports work when run as script
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo not in sys.path:
        sys.path.insert(0, repo)

    from scraper.config import R2_BUCKET
    from scraper.object_store import _s3_client, r2_configured

    if not r2_configured():
        print("R2 not configured", file=sys.stderr)
        return 2

    client = _s3_client()
    total_deleted = 0
    for prefix in PREFIXES:
        deleted = 0
        token = None
        while True:
            kwargs = {"Bucket": R2_BUCKET, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            objs = resp.get("Contents") or []
            if objs:
                # delete_objects max 1000
                for i in range(0, len(objs), 1000):
                    chunk = objs[i : i + 1000]
                    keys = [{"Key": o["Key"]} for o in chunk if o.get("Key")]
                    if not keys:
                        continue
                    client.delete_objects(
                        Bucket=R2_BUCKET,
                        Delete={"Objects": keys, "Quiet": True},
                    )
                    deleted += len(keys)
                    total_deleted += len(keys)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        print(f"prefix={prefix} deleted={deleted}")

    # Verify
    for prefix in PREFIXES:
        resp = client.list_objects_v2(Bucket=R2_BUCKET, Prefix=prefix, MaxKeys=5)
        n = len(resp.get("Contents") or [])
        print(f"verify prefix={prefix} remaining_sample={n}")
        if n:
            print("WARN: objects remain under", prefix, file=sys.stderr)

    print(f"r2_wipe_done total_deleted={total_deleted} bucket={R2_BUCKET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
