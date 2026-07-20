"""Backfill Hostinger media into R2 and rewrite ledger/export CDN URLs.

Usage:
  PYTHONPATH=. python -m scraper.media_backfill_r2 --dry-run
  PYTHONPATH=. python -m scraper.media_backfill_r2 --limit 100
  PYTHONPATH=. python -m scraper.media_backfill_r2 --from-hostinger --rewrite-ledger
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scraper.config import DEFAULT_JSON_OUT, DEFAULT_PIPELINE_LEDGER, REPO_ROOT
from scraper.media_urls import absolutize_export_media
from scraper.object_store import (
    public_object_url,
    r2_configured,
    upload_file,
)
from scraper.pipeline_ledger import (
    load_ledger,
    media_doc_path,
    public_doc_url,
    pull_ledger,
    push_ledger,
    write_ledger,
)

logger = logging.getLogger("scraper.media_backfill_r2")


def _phase(msg: str) -> None:
    print(f"[media_backfill] {msg}", flush=True)
    logger.info(msg)


def backfill_local_tree(
    public_dir: Path,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    uploaded = failed = skipped = 0
    count = 0
    for name in ("pdfs", "docs", "thumbs"):
        root = public_dir / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if limit is not None and count >= limit:
                return {"uploaded": uploaded, "failed": failed, "skipped": skipped}
            try:
                rel = str(path.relative_to(public_dir)).replace("\\", "/")
            except ValueError:
                continue
            count += 1
            if dry_run:
                skipped += 1
                continue
            up = upload_file(path, key=rel)
            if up.get("ok"):
                uploaded += 1
            else:
                failed += 1
                logger.warning("upload fail %s: %s", rel, up.get("error"))
    return {"uploaded": uploaded, "failed": failed, "skipped": skipped}


def rewrite_ledger_cdn(ledger_path: Path, *, dry_run: bool = False) -> int:
    ledger = load_ledger(ledger_path)
    n = 0
    for item in ledger.items:
        rel = media_doc_path(item)
        if not rel:
            continue
        cdn = public_object_url(rel) or public_doc_url(rel)
        if not cdn:
            continue
        changed = False
        if item.object_doc_url != cdn:
            item.object_doc_url = cdn
            changed = True
        if item.hostinger_doc_url != cdn:
            item.hostinger_doc_url = cdn
            changed = True
        if changed:
            n += 1
    if not dry_run and n:
        write_ledger(ledger, ledger_path)
    return n


def rewrite_export_cdn(export_path: Path, *, dry_run: bool = False) -> int:
    import json

    if not export_path.is_file():
        return 0
    data = json.loads(export_path.read_text(encoding="utf-8"))
    before = json.dumps(data.get("auctions") or [], sort_keys=True)
    absolutize_export_media(data)
    after = json.dumps(data.get("auctions") or [], sort_keys=True)
    if before == after:
        return 0
    if not dry_run:
        export_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(data.get("auctions") or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill media to R2 CDN")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--public-dir", default=str(REPO_ROOT / "web" / "public"))
    parser.add_argument("--rewrite-ledger", action="store_true")
    parser.add_argument("--rewrite-export", action="store_true")
    parser.add_argument("--pull-ledger", action="store_true")
    parser.add_argument("--push-ledger", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not r2_configured() and not args.dry_run:
        _phase("ERROR: R2 not configured")
        return 2

    if args.pull_ledger:
        pull_ledger(local_path=Path(DEFAULT_PIPELINE_LEDGER))

    public_dir = Path(args.public_dir)
    limit = int(args.limit) or None
    stats = backfill_local_tree(public_dir, limit=limit, dry_run=args.dry_run)
    _phase(f"local tree upload {stats}")

    if args.rewrite_ledger:
        n = rewrite_ledger_cdn(Path(DEFAULT_PIPELINE_LEDGER), dry_run=args.dry_run)
        _phase(f"ledger CDN rewrite rows={n}")
        if args.push_ledger and not args.dry_run:
            push_ledger(local_path=Path(DEFAULT_PIPELINE_LEDGER))

    if args.rewrite_export:
        n = rewrite_export_cdn(Path(DEFAULT_JSON_OUT), dry_run=args.dry_run)
        _phase(f"export CDN rewrite auctions={n}")

    return 0 if stats.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
