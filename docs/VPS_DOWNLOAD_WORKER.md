# VPS download workers (Phase C)

Run portal fetch on a small always-on VPS (preferably India egress for GeM).
GitHub Actions remains for orchestration/build-deploy; heavy download I/O moves here.

## Setup

1. Clone repo to `/opt/mstc-auction-listings` on the VPS.
2. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
3. Create `/etc/mstc-pipeline.env` with `HOSTINGER_*`, `SITE_BASE_URL`, Telegram, and optional `R2_*`.
4. `chmod +x scripts/download_worker.sh`
5. Install systemd units:

```bash
sudo cp scripts/systemd/mstc-download-worker.service /etc/systemd/system/
sudo cp scripts/systemd/mstc-download-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mstc-download-worker.timer
```

6. Optional second service for GeM (`download_worker.sh gem_forward 100`).

## Why

GHA runners hang on Hostinger SSH (exit 255 / half-open NAT). A VPS next to durable storage
keeps draining `fetched_local` via `pipeline_publish_media` even when Actions is stuck.
