# VPS MSTC download worker (MIYNU)

Sole **MSTC** downloader runs on the MIYNU VPS. GitHub Actions keeps Discover / Parse /
Build Deploy / GeM download. GHA `Lane Download MSTC` is **manual emergency only**
(no schedule).

## Host layout

| Path | Role |
|------|------|
| `/opt/viynu` | MIYNU product — **do not touch** |
| `/opt/mstc-pdf-experiment` | Probe harness only (not production scratch) |
| `/opt/mstc-auction-listings` | Pipeline clone + worker |
| `work/download_scratch/` | Ephemeral PDFs (deleted after R2 confirm) |
| `/etc/mstc-pipeline.env` | Secrets (Hostinger, R2, Telegram) |

## Flow

1. Pull Hostinger `pipeline_ledger.json`
2. Select `download_eligible` MSTC (12h runway)
3. Polite fetch (default concurrency **2**, gap **2s**)
4. Upload to R2 → CDN verify (`%PDF` / HTTP 200)
5. Mark ledger `download=done` + `object_doc_url`
6. Push ledger
7. Delete local PDFs
8. Health gate: ≥5 consecutive fails → abort wave (MSTC 500 storms)

Idempotent: if CDN already has `pdfs/{id}.pdf`, mark done without re-fetch.

## Setup

```bash
sudo mkdir -p /opt/mstc-auction-listings
sudo chown deploy:deploy /opt/mstc-auction-listings
git clone https://github.com/dheerajgodara/mstc-auction-listings.git /opt/mstc-auction-listings
cd /opt/mstc-auction-listings
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x scripts/download_worker.sh
```

Create `/etc/mstc-pipeline.env` (mode 600):

```bash
HOSTINGER_HOST=...
HOSTINGER_PORT=22
HOSTINGER_USERNAME=...
HOSTINGER_SSH_KEY=/home/deploy/.ssh/hostinger_key
HOSTINGER_REMOTE_DIR=...
SITE_BASE_URL=https://scrapauctionindia.com/auctions
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=scrapauction-pdfs
R2_PUBLIC_BASE_URL=https://files.csmg.in
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
MEDIA_R2_ONLY=1
```

Install systemd:

```bash
sudo cp scripts/systemd/mstc-download-worker.service /etc/systemd/system/
sudo cp scripts/systemd/mstc-download-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mstc-download-worker.timer
```

Manual smoke:

```bash
cd /opt/mstc-auction-listings
./scripts/download_worker.sh mstc 10
./scripts/download_worker.sh mstc 50   # speed check when portal is smooth
```

## Knobs

| Env | Default | Meaning |
|-----|---------|---------|
| `VPS_DOWNLOAD_GAP_SEC` | 2 | Sleep between micro-batches |
| `VPS_DOWNLOAD_CONCURRENCY` | 2 | Parallel portal fetches |
| `VPS_DOWNLOAD_FAIL_STREAK_ABORT` | 5 | Abort wave on consecutive fails |

## Why VPS

GHA runners were ~26 PDFs/h against MSTC. On this VPS, polite batching hit ~50 PDFs/min when the portal is healthy. Production worker adds R2 + ledger tax but keeps the same politeness recipe.
