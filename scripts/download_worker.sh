#!/usr/bin/env bash
# VPS download worker — run under systemd/cron on an always-on box (Phase C).
# Prefer India egress for GeM; keep Hostinger only as storage/publish target.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"
export PYTHONPATH=.
export PYTHONUNBUFFERED=1
export DOWNLOAD_DECOUPLE_FLUSH="${DOWNLOAD_DECOUPLE_FLUSH:-1}"
export DOWNLOAD_STALL_ABORT_MIN="${DOWNLOAD_STALL_ABORT_MIN:-20}"
export DOWNLOAD_WAVE_DEADLINE_SEC="${DOWNLOAD_WAVE_DEADLINE_SEC:-600}"
export SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-15}"
export RSYNC_IO_TIMEOUT="${RSYNC_IO_TIMEOUT:-120}"

SOURCE="${1:-mstc}"
CAP="${2:-200}"

echo "[download_worker] source=$SOURCE cap=$CAP $(date -u +%Y-%m-%dT%H:%M:%SZ)"
python -m scraper.pipeline_download \
  --source "$SOURCE" \
  --wave-size 25 \
  --batch-size 25 \
  --max-batches 40 \
  --max-download "$CAP" \
  --break-stale-lock

# Drain any fetched_local left by Hostinger blips
python -m scraper.pipeline_publish_media --wave-size 50 --max-waves 20 --break-stale-lock
