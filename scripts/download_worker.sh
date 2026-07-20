#!/usr/bin/env bash
# MIYNU VPS MSTC download worker — polite fetch → R2 verify → ledger → delete local.
# Does not touch /opt/viynu. Production clone: /opt/mstc-auction-listings
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"
export PYTHONPATH=.
export PYTHONUNBUFFERED=1
export MEDIA_R2_ONLY="${MEDIA_R2_ONLY:-1}"
export DOWNLOAD_DECOUPLE_FLUSH="${DOWNLOAD_DECOUPLE_FLUSH:-0}"
export VPS_DOWNLOAD_GAP_SEC="${VPS_DOWNLOAD_GAP_SEC:-2}"
export VPS_DOWNLOAD_CONCURRENCY="${VPS_DOWNLOAD_CONCURRENCY:-2}"
export VPS_DOWNLOAD_FAIL_STREAK_ABORT="${VPS_DOWNLOAD_FAIL_STREAK_ABORT:-5}"
export SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-15}"
export RSYNC_IO_TIMEOUT="${RSYNC_IO_TIMEOUT:-120}"

# Keep argv compatible: download_worker.sh [source] [cap]
SOURCE="${1:-mstc}"
CAP="${2:-150}"

if [ "$SOURCE" != "mstc" ]; then
  echo "[download_worker] GeM on VPS is out of scope this phase; refusing source=$SOURCE" >&2
  exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[download_worker] vps_mstc source=$SOURCE cap=$CAP gap=${VPS_DOWNLOAD_GAP_SEC}s concurrency=${VPS_DOWNLOAD_CONCURRENCY} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec "$PYTHON_BIN" -m scraper.vps_mstc_download \
  --max-download "$CAP" \
  --gap-sec "${VPS_DOWNLOAD_GAP_SEC}" \
  --concurrency "${VPS_DOWNLOAD_CONCURRENCY}" \
  --fail-streak-abort "${VPS_DOWNLOAD_FAIL_STREAK_ABORT}" \
  --break-stale-lock
