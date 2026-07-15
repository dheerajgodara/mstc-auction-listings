# 3-job pipeline runbook

## Jobs

1. **Download** (`pipeline-download.yml`) — discovery + raw HTML/PDF/docs. Cap **200** catch-up / **100** steady.
2. **Parse** (`pipeline-parse.yml`) — parse from disk (MSTC) or live enrich (GeM/eAuction); promote `auctions.json`.
3. **Deploy** (`pipeline-deploy.yml`) — `build:prod` + verify + Hostinger rsync every 3h IST.

## Durable state (Hostinger)

- `{domain_root}/auction_pipeline/pipeline_ledger.json`
- `{domain_root}/auction_pipeline/raw/{source}/{id}.html`
- Public media unchanged: `…/public_html/auctions/{pdfs,docs,thumbs}`

## Ops

- Watch Telegram: `download_*`, `parse_*`, `deploy_*` events and Ledger section.
- Catch-up: keep `max_download=200` until **MSTC** download pending &lt; 100, then switch dispatch/default to **100**.
- Download cap is **MSTC-only**. GeM/eAuction skip the raw download stage and enter parse via a single live batch enrich per source.
- Parse pulls only selected raw HTML + `pdfs/` (not full docs/thumbs trees).
- Legacy monolith `refresh-and-deploy.yml` is **manual emergency only** (no schedule).
- Locks are independent: `work/download.lock`, `work/parse.lock`, `work/deploy.lock`.

## Manual triggers

```bash
gh workflow run pipeline-download.yml -f max_download=200
gh workflow run pipeline-parse.yml
gh workflow run pipeline-deploy.yml
```
