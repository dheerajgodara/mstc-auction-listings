"""Independent Parse lane: one-by-one PDF/HTML parse → durable parse cache."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scraper.config import (
    DEFAULT_PARSED_DIR,
    DEFAULT_PDF_DIR,
    DEFAULT_PIPELINE_LEDGER,
    DEFAULT_RAW_DIR,
    PARSE_FAIL_BUDGET_ABS,
    PARSE_FAIL_BUDGET_PCT,
    PARSER_CACHE_VERSION,
    PIPELINE_JOB_TIMEBOX_MIN,
    REPO_ROOT,
)
from scraper.filters import make_run_id
from scraper.lane_resume import dispatch_workflow, record_resume, should_self_resume
from scraper.main import enrich_auction, resolve_auction_listing
from scraper.parse_cache import (
    build_parse_artifact,
    file_sha256,
    is_fresh_parse,
    load_parse_artifact,
    local_parsed_path,
    pull_parsed_tree,
    push_parsed_file,
    write_parse_artifact,
)
from scraper.pipeline_ledger import (
    fail_budget_ok,
    load_ledger,
    mark_parse,
    pull_ledger,
    push_ledger,
    select_for_parse,
    write_ledger,
)
from scraper.raw_store import pull_public_pdf_files, pull_raw_files
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_lane_report
from scraper.models import AuctionRecord

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_parse_assets")


def _phase(msg: str) -> None:
    print(f"[parse_assets] {msg}", flush=True)
    logger.info(msg)


def _parse_id_set(raw: str | None) -> set[str] | None:
    if not raw or not str(raw).strip():
        return None
    ids = {p.strip() for p in str(raw).split(",") if p.strip()}
    return ids or None


def run_parse_assets(
    *,
    repo_root: Path = REPO_ROOT,
    timebox_min: int = PIPELINE_JOB_TIMEBOX_MIN,
    break_stale_lock: bool = True,
    max_parse: int | None = None,
    auction_ids: str | None = None,
) -> dict[str, Any]:
    run_id = f"parse_assets_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(run_dir / "parse_assets.log", encoding="utf-8"),
        ],
        force=True,
    )

    lock_path = repo_root / "work" / "parse_assets.lock"
    acquire_refresh_lock(
        lock_path=lock_path, run_id=run_id, stale_minutes=360, break_stale_lock=break_stale_lock
    )

    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    pdf_dir = Path(DEFAULT_PDF_DIR)
    raw_dir = Path(DEFAULT_RAW_DIR)
    parsed_root = Path(DEFAULT_PARSED_DIR)
    public_dir = repo_root / "web" / "public"
    t0 = time.monotonic()
    parsed_n = skipped = failed = 0
    capped_run = max_parse is not None and int(max_parse) > 0
    id_filter = _parse_id_set(auction_ids)
    attempted_ids: list[str] = []

    try:
        pull_ledger(local_path=ledger_path)
        pull_parsed_tree(local_root=parsed_root)
        ledger = load_ledger(ledger_path)
        queue = select_for_parse(ledger, limit=None)
        if id_filter is not None:
            queue = [i for i in queue if str(i.source_auction_id) in id_filter]
            _phase(f"auction_ids filter={sorted(id_filter)} matched={len(queue)}")
        if capped_run:
            queue = queue[: int(max_parse)]
        _phase(f"queue={len(queue)} max_parse={max_parse}")

        mstc_items = [i for i in queue if i.source == "mstc"]
        if mstc_items:
            _phase(f"bootstrap: pull raw+pdf for {len(mstc_items)} MSTC id(s)")
            pull_raw_files(
                [(i.source, i.source_auction_id) for i in mstc_items],
                raw_dir=raw_dir,
                timeout_sec=300,
            )
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pull_public_pdf_files(
                public_dir=public_dir,
                filenames=[f"{i.source_auction_id}.pdf" for i in mstc_items],
            )

        for item in queue:
            elapsed_min = (time.monotonic() - t0) / 60.0
            if elapsed_min >= timebox_min:
                _phase("timebox reached")
                break

            aid = item.source_auction_id
            src = item.source
            attempted_ids.append(str(aid))
            out_path = local_parsed_path(src, aid, root=parsed_root)
            pdf_path = pdf_dir / f"{aid}.pdf"
            pdf_hash = file_sha256(pdf_path) if pdf_path.is_file() else None
            existing = load_parse_artifact(out_path)
            if is_fresh_parse(
                existing, pdf_sha256=pdf_hash, parser_version=PARSER_CACHE_VERSION
            ):
                skipped += 1
                if item.parse != "done":
                    mark_parse(
                        ledger,
                        item.stable_key,
                        ok=True,
                        error=None,
                    )
                    # enrich mark_parse may not set parsed_path — patch below
                    it = ledger.by_key().get(item.stable_key)
                    if it:
                        it.parsed_path = f"parsed/{src}/{aid}.json"
                        it.parsed_at = datetime.now(IST).isoformat()
                        it.pdf_sha256 = pdf_hash
                        it.parser_version = PARSER_CACHE_VERSION
                        it.parse = "done"
                write_ledger(ledger, ledger_path)
                continue

            try:
                if src == "mstc":
                    base, _meta = resolve_auction_listing(aid)
                    record = enrich_auction(
                        base,
                        pdf_dir=pdf_dir,
                        skip_pdf=False,
                        stats={},
                        mode="parse_only",
                        raw_dir=raw_dir,
                    )
                    rec = record.model_dump(mode="json")
                else:
                    from scraper.pipeline_parse import _enrich_non_mstc_batch

                    batch = _enrich_non_mstc_batch("gem_forward", {aid})
                    record = batch.get(aid)
                    if record is None:
                        raise RuntimeError(f"gem enrich returned nothing for {aid}")
                    rec = (
                        record.model_dump(mode="json")
                        if isinstance(record, AuctionRecord)
                        else dict(record)
                    )

                lots = rec.get("lots") or []
                ok = isinstance(lots, list) and len(lots) > 0
                artifact = build_parse_artifact(
                    record=rec,
                    stable_key=item.stable_key,
                    pdf_sha256=pdf_hash,
                    parser_version=PARSER_CACHE_VERSION,
                )
                write_parse_artifact(out_path, artifact)
                push_parsed_file(out_path, source=src, source_auction_id=aid)
                mark_parse(ledger, item.stable_key, ok=ok, deploy_ready=ok, error=None if ok else "no lots")
                it = ledger.by_key().get(item.stable_key)
                if it:
                    it.parsed_path = f"parsed/{src}/{aid}.json"
                    it.parsed_at = datetime.now(IST).isoformat()
                    it.pdf_sha256 = pdf_hash
                    it.parser_version = PARSER_CACHE_VERSION
                    it.parse_last_error = None if ok else "no lots"
                    if ok:
                        it.build = "pending"
                write_ledger(ledger, ledger_path)
                push_ledger(local_path=ledger_path)
                _phase(f"parse_item source={src} id={aid} ok={ok} lots={len(lots) if ok else 0}")
                if ok:
                    parsed_n += 1
                else:
                    failed += 1
            except Exception as exc:
                logger.exception("parse failed %s", item.stable_key)
                mark_parse(ledger, item.stable_key, ok=False, error=str(exc))
                it = ledger.by_key().get(item.stable_key)
                if it:
                    it.parse_last_error = str(exc)
                write_ledger(ledger, ledger_path)
                push_ledger(local_path=ledger_path)
                failed += 1
                _phase(f"parse_item source={src} id={aid} ok=False error={exc}")

        backlog = len(select_for_parse(load_ledger(ledger_path), limit=None))
        attempted = parsed_n + failed
        budget_ok = fail_budget_ok(
            failed=failed,
            attempted=attempted,
            pct=PARSE_FAIL_BUDGET_PCT,
            absolute=PARSE_FAIL_BUDGET_ABS,
        )
        elapsed_min = (time.monotonic() - t0) / 60.0
        resume = False
        reason = "capped_or_filtered" if (capped_run or id_filter is not None) else ""
        if not capped_run and id_filter is None:
            resume, reason = should_self_resume(
                backlog_left=backlog,
                failed=failed,
                attempted=attempted,
                fail_budget_ok=budget_ok,
                elapsed_min=elapsed_min,
                timebox_min=timebox_min,
            )
            if resume:
                record_resume("parse", {"reason": reason, "backlog_left": backlog})
                dispatch_workflow("pipeline-parse-assets.yml")

        status = "Complete" if backlog == 0 else "Paused · timebox"
        send_lane_report(
            "parse",
            "finished",
            {
                "status": status,
                "parsed": parsed_n,
                "skipped_fresh": skipped,
                "failed": failed,
                "backlog_left": backlog,
                "resume_next": resume,
            },
            noop=attempted == 0 and skipped == 0 and backlog == 0,
        )
        payload = {
            "run_id": run_id,
            "parsed": parsed_n,
            "skipped": skipped,
            "failed": failed,
            "attempted_ids": attempted_ids,
            "max_parse": max_parse,
            "auction_ids": sorted(id_filter) if id_filter else None,
            "backlog_left": backlog,
            "resume": resume,
            "resume_reason": reason,
        }
        if attempted_ids:
            _phase(f"attempted_ids={','.join(attempted_ids)}")
        (run_dir / "parse_assets_report.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return payload
    except Exception as exc:
        send_lane_report("parse", "failed", {"error": str(exc), "backlog_left": "?"})
        raise
    finally:
        release_refresh_lock(lock_path=lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse assets lane (one-by-one)")
    parser.add_argument("--timebox-min", type=int, default=PIPELINE_JOB_TIMEBOX_MIN)
    parser.add_argument("--max-parse", type=int, default=None)
    parser.add_argument(
        "--auction-ids",
        default=None,
        help="Comma-separated source_auction_id filter (smoke / targeted parse)",
    )
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_parse_assets(
        timebox_min=args.timebox_min,
        break_stale_lock=args.break_stale_lock,
        max_parse=args.max_parse,
        auction_ids=args.auction_ids,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
