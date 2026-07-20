#!/usr/bin/env bash
# Fresh-start Hostinger wipe: rename auction_pipeline (+ optional AI state),
# clear public catalogue JSON and legacy media dirs. Keeps Next.js shell.
set -euo pipefail

CONFIRM="${CONFIRM:-}"
WIPE_AI="${WIPE_AI:-1}"
WIPE_PUBLIC_MEDIA="${WIPE_PUBLIC_MEDIA:-1}"
WIPE_PUBLIC_DATA="${WIPE_PUBLIC_DATA:-1}"
HARD_DELETE_BAK="${HARD_DELETE_BAK:-0}"

if [[ "$CONFIRM" != "WIPE-PRODUCTION" ]]; then
  echo "Refusing: set CONFIRM=WIPE-PRODUCTION" >&2
  exit 2
fi

: "${HOSTINGER_HOST:?}"
: "${HOSTINGER_PORT:?}"
: "${HOSTINGER_USERNAME:?}"
: "${HOSTINGER_SSH_KEY:?}"
: "${HOSTINGER_REMOTE_DIR:?}"

KEY=$(eval echo "$HOSTINGER_SSH_KEY")
REMOTE_DIR="${HOSTINGER_REMOTE_DIR%/}"
# domain_root = everything before /public_html/
if [[ "$REMOTE_DIR" == *"/public_html/"* ]]; then
  DOMAIN_ROOT="${REMOTE_DIR%%/public_html/*}"
else
  DOMAIN_ROOT=$(dirname "$(dirname "$REMOTE_DIR")")
fi
PIPELINE="${DOMAIN_ROOT}/auction_pipeline"
AI_STATE="${DOMAIN_ROOT}/ai_enrichment_state"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BAK="${PIPELINE}.bak.${STAMP}"

SSH=(ssh -i "$KEY" -p "$HOSTINGER_PORT"
  -o StrictHostKeyChecking=accept-new
  -o BatchMode=yes
  -o ConnectTimeout=20
  -o ServerAliveInterval=30
  "${HOSTINGER_USERNAME}@${HOSTINGER_HOST}")

echo "domain_root=$DOMAIN_ROOT"
echo "pipeline=$PIPELINE"
echo "remote_dir=$REMOTE_DIR"

remote() {
  "${SSH[@]}" "$@"
}

echo "=== rename auction_pipeline -> $BAK ==="
remote "if [ -d '$PIPELINE' ]; then mv '$PIPELINE' '$BAK' && echo renamed_ok; else echo pipeline_absent; fi"

if [[ "$WIPE_AI" == "1" ]]; then
  AI_BAK="${AI_STATE}.bak.${STAMP}"
  echo "=== rename ai_enrichment_state -> $AI_BAK ==="
  remote "if [ -d '$AI_STATE' ]; then mv '$AI_STATE' '$AI_BAK' && echo ai_renamed_ok; else echo ai_absent; fi"
fi

if [[ "$WIPE_PUBLIC_DATA" == "1" ]]; then
  echo "=== wipe public catalogue data JSON ==="
  remote "cd '$REMOTE_DIR' && rm -f data/auctions.json data/auctions-data.js data/auctions.min.json 2>/dev/null; ls data 2>/dev/null | head -40 || echo no_data_dir"
fi

if [[ "$WIPE_PUBLIC_MEDIA" == "1" ]]; then
  echo "=== wipe legacy public pdfs/docs/thumbs (dirs recreated empty) ==="
  remote "cd '$REMOTE_DIR' && rm -rf pdfs docs thumbs && mkdir -p pdfs docs/gem thumbs && echo media_dirs_reset"
fi

if [[ "$HARD_DELETE_BAK" == "1" ]]; then
  echo "=== hard-delete bak (irreversible) ==="
  remote "rm -rf '$BAK' '${AI_STATE}.bak.${STAMP}' 2>/dev/null; echo bak_deleted"
else
  echo "=== bak retained for 7d rollback: $BAK ==="
fi

echo "=== verify ==="
remote "test ! -e '$PIPELINE/pipeline_ledger.json' && echo no_ledger_ok || echo LEDGER_STILL_PRESENT; ls -la '$DOMAIN_ROOT' | head -30"
echo "hostinger_wipe_done"
