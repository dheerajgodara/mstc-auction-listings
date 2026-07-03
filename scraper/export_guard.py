from __future__ import annotations

import json
from pathlib import Path

MIN_PROTECTED_AUCTION_COUNT = 100

PROTECTED_EXPORT_PATHS: tuple[Path, ...] = (
    Path("web/public/data/auctions.json"),
    Path("web/out/data/auctions.json"),
)


class ExportGuardError(RuntimeError):
    pass


def _normalize(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def is_protected_export_path(path: Path, *, repo_root: Path | None = None) -> bool:
    target = _normalize(path)
    root = _normalize(repo_root) if repo_root else None
    for protected in PROTECTED_EXPORT_PATHS:
        candidate = _normalize(protected)
        if root:
            candidate = _normalize(root / protected)
        if target == candidate:
            return True
    return False


def validate_export_write(
    path: Path,
    auction_count: int,
    *,
    allow_small_output: bool = False,
    repo_root: Path | None = None,
) -> None:
    if not is_protected_export_path(path, repo_root=repo_root):
        return
    if auction_count < MIN_PROTECTED_AUCTION_COUNT and not allow_small_output:
        raise ExportGuardError(
            f"Refusing to write {auction_count} auctions to protected path {path}. "
            f"Minimum is {MIN_PROTECTED_AUCTION_COUNT} unless --allow-small-output is set."
        )


def write_auctions_json(
    path: Path,
    payload: dict,
    *,
    allow_small_output: bool = False,
    repo_root: Path | None = None,
) -> None:
    count = payload.get("count")
    if count is None:
        count = len(payload.get("auctions") or [])
    validate_export_write(
        path,
        int(count),
        allow_small_output=allow_small_output,
        repo_root=repo_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
