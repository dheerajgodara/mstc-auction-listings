"""Orchestrate Parse(100) → Deploy cycles until parse backlog is cleared."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from scraper.config import (
    DEFAULT_PIPELINE_LEDGER,
    PIPELINE_DRAIN_DEPLOY_RETRIES,
    PIPELINE_DRAIN_MAX_CYCLES,
    PIPELINE_DRAIN_PARSE_RETRIES,
    PIPELINE_PARSE_CAP_DEFAULT,
    REPO_ROOT,
    SITE_BASE_URL,
)
from scraper.filters import make_run_id
from scraper.pipeline_deploy import run_pipeline_deploy
from scraper.pipeline_ledger import load_ledger, pull_ledger, select_for_parse
from scraper.pipeline_parse import run_pipeline_parse
from scraper.refresh_lock import acquire_refresh_lock, release_refresh_lock
from scraper.telegram_reporter import send_telegram_report

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("scraper.pipeline_drain")


def _github_run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def _setup_logging(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(run_dir / "drain.log", encoding="utf-8"),
        ],
        force=True,
    )


def _phase(msg: str) -> None:
    print(f"[pipeline_drain] {msg}", flush=True)
    logger.info(msg)


def parse_backlog_count(ledger) -> int:
    return len(select_for_parse(ledger, limit=None))


def compute_max_cycles(backlog: int, *, hard_cap: int = PIPELINE_DRAIN_MAX_CYCLES) -> int:
    if backlog <= 0:
        return 0
    return min(hard_cap, int(math.ceil(backlog / 100)) + 2)


def _call_with_retries(
    label: str,
    fn: Callable[[], dict[str, Any]],
    *,
    max_attempts: int,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    last_err: str | None = None
    last_payload: dict[str, Any] | None = None
    for attempt in range(1, max_attempts + 1):
        _phase(f"{label} attempt {attempt}/{max_attempts}")
        try:
            last_payload = fn()
            if (last_payload or {}).get("status") == "failed":
                last_err = str((last_payload or {}).get("errors") or ["status=failed"])
                _phase(f"{label} reported failed: {last_err}")
                continue
            return True, last_payload, None
        except Exception as exc:
            last_err = str(exc)
            logger.exception("%s failed attempt %s", label, attempt)
            if attempt < max_attempts:
                # Tests may set PIPELINE_DRAIN_RETRY_SLEEP_SEC=0 to skip backoff.
                delay = float(os.environ.get("PIPELINE_DRAIN_RETRY_SLEEP_SEC", str(min(30 * attempt, 120))))
                if delay > 0:
                    time.sleep(delay)
    return False, last_payload, last_err


def run_pipeline_drain(
    *,
    repo_root: Path = REPO_ROOT,
    max_parse: int = PIPELINE_PARSE_CAP_DEFAULT,
    max_cycles: int | None = None,
    parse_retries: int = PIPELINE_DRAIN_PARSE_RETRIES,
    deploy_retries: int = PIPELINE_DRAIN_DEPLOY_RETRIES,
    break_stale_lock: bool = True,
    parse_fn: Callable[..., dict[str, Any]] | None = None,
    deploy_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parse_fn = parse_fn or run_pipeline_parse
    deploy_fn = deploy_fn or run_pipeline_deploy

    run_id = f"drain_{make_run_id()}"
    run_dir = repo_root / "work" / "runs" / run_id
    _setup_logging(run_dir)
    lock_path = repo_root / "work" / "drain.lock"
    acquire_refresh_lock(lock_path=lock_path, run_id=run_id, stale_minutes=400, break_stale_lock=break_stale_lock)

    ledger_path = Path(DEFAULT_PIPELINE_LEDGER)
    started = datetime.now(IST).isoformat()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "pipeline": "drain",
        "started_at": started,
        "max_parse": max_parse,
        "site_base_url": SITE_BASE_URL,
        "github_run_url": _github_run_url(),
        "cycles": [],
        "warnings": [],
        "errors": [],
    }

    try:
        pull_ledger(local_path=ledger_path)
        ledger = load_ledger(ledger_path)
        backlog = parse_backlog_count(ledger)
        cycles_cap = max_cycles if max_cycles is not None else compute_max_cycles(backlog)
        payload["parse_backlog_start"] = backlog
        payload["max_cycles"] = cycles_cap
        payload["ledger"] = ledger.status_counts()
        send_telegram_report(payload, event="drain_started")
        _phase(f"start backlog={backlog} max_cycles={cycles_cap} max_parse={max_parse}")

        if backlog <= 0 or cycles_cap <= 0:
            payload.update(
                {
                    "status": "success",
                    "finished_at": datetime.now(IST).isoformat(),
                    "cycles_completed": 0,
                    "message": "no parse backlog",
                }
            )
            (run_dir / "drain_report.json").write_text(
                json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
            )
            send_telegram_report(payload, event="drain_done")
            return payload

        cycles_completed = 0
        recoverable_parse_errors = 0
        for cycle in range(1, cycles_cap + 1):
            pull_ledger(local_path=ledger_path)
            ledger = load_ledger(ledger_path)
            remaining = parse_backlog_count(ledger)
            if remaining <= 0:
                _phase("parse backlog empty — drain complete")
                break

            cycle_info: dict[str, Any] = {"cycle": cycle, "remaining_before": remaining}
            _phase(f"cycle {cycle}/{cycles_cap} remaining={remaining}")

            ok, parse_payload, parse_err = _call_with_retries(
                "parse",
                lambda: parse_fn(
                    max_parse=max_parse,
                    promote=True,
                    break_stale_lock=True,
                ),
                max_attempts=parse_retries,
            )
            recovered = int((parse_payload or {}).get("recoverable_parse_errors") or 0)
            recoverable_parse_errors += recovered
            cycle_info["parse"] = {
                "ok": ok,
                "selected": (parse_payload or {}).get("selected_count"),
                "parse_ok": (parse_payload or {}).get("parse_ok"),
                "parse_failed": (parse_payload or {}).get("parse_failed"),
                "recoverable_parse_errors": recovered,
                "dropped_aged_out": (parse_payload or {}).get("dropped_aged_out"),
                "error": parse_err,
            }
            if not ok:
                payload["status"] = "stopped"
                payload["errors"] = [f"parse retries exhausted: {parse_err}"]
                payload["recoverable_parse_errors"] = recoverable_parse_errors
                payload["cycles"].append(cycle_info)
                payload["finished_at"] = datetime.now(IST).isoformat()
                payload["cycles_completed"] = cycles_completed
                payload["ledger"] = load_ledger(ledger_path).status_counts()
                (run_dir / "drain_report.json").write_text(
                    json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
                )
                send_telegram_report(payload, event="drain_stopped")
                raise RuntimeError(payload["errors"][0])

            selected = int((parse_payload or {}).get("selected_count") or 0)
            if selected <= 0:
                payload["cycles"].append(cycle_info)
                _phase("parse selected 0 — drain complete")
                break

            ok, deploy_payload, deploy_err = _call_with_retries(
                "deploy",
                lambda: deploy_fn(deploy=True, break_stale_lock=True, force=False),
                max_attempts=deploy_retries,
            )
            cycle_info["deploy"] = {
                "ok": ok,
                "status": (deploy_payload or {}).get("status"),
                "skipped": (deploy_payload or {}).get("deploy_skipped_unchanged"),
                "error": deploy_err,
            }
            if not ok:
                payload["status"] = "stopped"
                payload["errors"] = [f"deploy retries exhausted: {deploy_err}"]
                payload["recoverable_parse_errors"] = recoverable_parse_errors
                payload["cycles"].append(cycle_info)
                payload["finished_at"] = datetime.now(IST).isoformat()
                payload["cycles_completed"] = cycles_completed
                payload["ledger"] = load_ledger(ledger_path).status_counts()
                (run_dir / "drain_report.json").write_text(
                    json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
                )
                send_telegram_report(payload, event="drain_stopped")
                raise RuntimeError(payload["errors"][0])

            cycles_completed += 1
            pull_ledger(local_path=ledger_path)
            cycle_info["remaining_after"] = parse_backlog_count(load_ledger(ledger_path))
            payload["cycles"].append(cycle_info)
            payload["ledger"] = load_ledger(ledger_path).status_counts()
            send_telegram_report(
                {
                    **payload,
                    "cycle": cycle,
                    "cycles_completed": cycles_completed,
                    "parse_ok": cycle_info["parse"].get("parse_ok"),
                    "remaining_after": cycle_info["remaining_after"],
                },
                event="drain_cycle",
            )

        pull_ledger(local_path=ledger_path)
        final_ledger = load_ledger(ledger_path)
        payload.update(
            {
                "status": "success",
                "finished_at": datetime.now(IST).isoformat(),
                "cycles_completed": cycles_completed,
                "parse_backlog_end": parse_backlog_count(final_ledger),
                "recoverable_parse_errors": recoverable_parse_errors,
                "ledger": final_ledger.status_counts(),
            }
        )
        (run_dir / "drain_report.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
        send_telegram_report(payload, event="drain_done")
        return payload
    except Exception:
        if payload.get("status") not in {"stopped", "success"}:
            payload["status"] = "failed"
            payload["finished_at"] = datetime.now(IST).isoformat()
            send_telegram_report(payload, event="drain_stopped")
        raise
    finally:
        release_refresh_lock(lock_path, run_id=run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drain: parse 100 → deploy until backlog clear")
    parser.add_argument("--max-parse", type=int, default=PIPELINE_PARSE_CAP_DEFAULT)
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--parse-retries", type=int, default=PIPELINE_DRAIN_PARSE_RETRIES)
    parser.add_argument("--deploy-retries", type=int, default=PIPELINE_DRAIN_DEPLOY_RETRIES)
    parser.add_argument("--break-stale-lock", action="store_true", default=True)
    args = parser.parse_args(argv)
    run_pipeline_drain(
        max_parse=args.max_parse,
        max_cycles=args.max_cycles,
        parse_retries=args.parse_retries,
        deploy_retries=args.deploy_retries,
        break_stale_lock=args.break_stale_lock,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
