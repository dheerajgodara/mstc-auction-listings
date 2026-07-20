#!/usr/bin/env python3
"""Autonomy tick policy: lanes run independently / simultaneously.

Only cancel duplicate runs of the *same* workflow. Never cancel peer lanes
(Discover/Parse/GeM/Deploy) for SSH preference.

Usage:
  python3 scripts/autonomy_tick_policy.py           # plan only
  python3 scripts/autonomy_tick_policy.py --apply   # cancel duplicates via gh
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ACTIVE = ("in_progress", "queued", "pending", "waiting")
STATUS_DIR = Path("/tmp/mstc_status")


def _runs() -> list[dict]:
    raw = subprocess.check_output(
        [
            "gh",
            "run",
            "list",
            "--limit",
            "40",
            "--json",
            "databaseId,status,conclusion,workflowName,createdAt",
        ],
        text=True,
        timeout=60,
    )
    return json.loads(raw)


def dedupe_same_workflow(runs: list[dict]) -> list[str]:
    """Keep newest run per Lane workflow; cancel older duplicates."""
    by_name: dict[str, list[dict]] = {}
    for r in runs:
        name = r.get("workflowName") or ""
        if not name.startswith("Lane "):
            continue
        if r.get("status") not in ACTIVE:
            continue
        by_name.setdefault(name, []).append(r)
    actions: list[str] = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
        for r in group[1:]:
            actions.append(f"cancel_duplicate:{r['databaseId']}")
    return actions


def apply_actions(actions: list[str]) -> list[str]:
    applied: list[str] = []
    for action in actions:
        if not action.startswith("cancel_duplicate:"):
            continue
        run_id = action.split(":", 1)[1]
        try:
            subprocess.check_call(
                ["gh", "run", "cancel", run_id],
                timeout=60,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            applied.append(action)
        except Exception as exc:
            applied.append(f"cancel_failed:{run_id}:{exc}")
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute cancel_duplicate actions (never cancels peer lanes)",
    )
    args = parser.parse_args()

    runs = _runs()
    actions = dedupe_same_workflow(runs)
    # Independent lanes: never emit cancel_ssh / prefer-download peer cancels.
    applied: list[str] = []
    if args.apply and actions:
        applied = apply_actions(actions)

    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (STATUS_DIR / "autonomy_actions.txt").write_text(
        "\n".join(dict.fromkeys(actions)) + ("\n" if actions else "")
    )
    state = {
        "mode": "independent_lanes",
        "cancel_peer_lanes": False,
        "prefer_download_cancel": False,
        "actions": actions,
        "applied": applied,
    }
    (STATUS_DIR / "autonomy_policy.json").write_text(json.dumps(state, indent=2) + "\n")
    # Merge into autonomy_state without wiping live counters.
    state_path = STATUS_DIR / "autonomy_state.json"
    existing: dict = {}
    if state_path.exists():
        try:
            existing = json.loads(state_path.read_text())
        except Exception:
            existing = {}
    existing.update(
        {
            "mode": "independent_lanes",
            "cancel_peer_lanes": False,
            "prefer_download_until": None,
            "policy_ts": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }
    )
    state_path.write_text(json.dumps(existing, indent=2) + "\n")
    print(json.dumps(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
