"""Extract actionable FAIL lines from verify-build / pnpm output."""

from __future__ import annotations

import re

_FAIL_LINE_RE = re.compile(r"^\s*FAIL\s+(.+)$", re.MULTILINE)
_ELIFECYCLE_RE = re.compile(r"ELIFECYCLE.*?failed with exit code\s+\d+", re.IGNORECASE)


def extract_fail_lines(output: str, *, limit: int = 3) -> list[str]:
    """Return up to `limit` unique FAIL check labels from verifier stdout/stderr."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _FAIL_LINE_RE.finditer(output or ""):
        label = " ".join(match.group(1).split())
        if not label or label in seen:
            continue
        seen.add(label)
        found.append(label)
        if len(found) >= limit:
            break
    return found


def summarize_command_failure(
    cmd: list[str] | str,
    *,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
    fail_limit: int = 3,
) -> tuple[str, list[str], str]:
    """Build a short error summary plus FAIL labels and a longer log tail.

    Returns (short_error, fail_labels, log_tail).
    """
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
    combined = f"{stdout or ''}\n{stderr or ''}"
    fails = extract_fail_lines(combined, limit=fail_limit)
    tail = combined[-4000:] if combined.strip() else ""

    if fails:
        joined = "; ".join(f"FAIL {label}" for label in fails)
        short = f"{cmd_str}: {joined}"
    elif _ELIFECYCLE_RE.search(combined):
        short = f"command failed ({returncode}): {cmd_str} (ELIFECYCLE — see log)"
    else:
        short = f"command failed ({returncode}): {cmd_str}"
    return short, fails, tail
