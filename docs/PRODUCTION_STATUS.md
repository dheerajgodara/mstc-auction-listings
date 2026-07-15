# Production status

## Live site

- **URL:** https://scrapauctionindia.com/auctions/
- **Host:** Hostinger static export at `domains/scrapauctionindia.com/public_html/auctions`
- **Canonical domain only:** `scrapauctionindia.com`. Hostinger preview subdomains are not production and must not receive scheduled auction deploys.

## Production workflow (authoritative) — 3-job pipeline

Scheduled production uses three independent jobs:

| Job | Workflow | Module | Schedule |
|-----|----------|--------|----------|
| **1. Download** | `.github/workflows/pipeline-download.yml` | `scraper.pipeline_download` | `30 0,6,12,18 * * *` UTC (= **00/06/12/18 IST**) |
| **2. Parse** | `.github/workflows/pipeline-parse.yml` | `scraper.pipeline_parse` | after download success + every 3h UTC catch-up |
| **3. Deploy** | `.github/workflows/pipeline-deploy.yml` | `scraper.pipeline_deploy` | `30 */3 * * *` UTC (= every **3h at :00 IST**) |

- **Download cap:** catch-up default **200**/run (**MSTC-only**); steady-state **100**/run once MSTC `download=pending` &lt; 100
- **Ledger:** Hostinger `{domain}/auction_pipeline/pipeline_ledger.json` + local `work/pipeline_ledger.json`
- **Raw HTML:** Hostinger `{domain}/auction_pipeline/raw/{source}/{id}.html` (private); PDFs/docs/thumbs stay public under `auctions/`
- **Safety gates:** run on **Parse → promote** (min count 1000, multi-source, drop protection)
- **Deploy** builds/verifies from promoted `auctions.json` and rsyncs `web/out/` (media dirs protected from `--delete`)
- **Legacy monolith:** `.github/workflows/refresh-and-deploy.yml` is **manual emergency only** (no cron)
- **Cutover soak (2026-07-15):** Download `29410139656`+`29422935839` (400 raw done, ~990 MSTC pending); Parse `29426436750` (200 ok / 200 deploy_ready); Deploy `29427951887` success. Ops details: `docs/PIPELINE_RUNBOOK.md`

### Catch-up vs steady-state

- **Catch-up:** leave download cap at **200** until Telegram ledger shows **MSTC** pending downloads &lt; 100
- **Steady-state:** set workflow default / dispatch `max_download=100`
- Failed deploy no longer blocks download progress (stages retry independently)

## AI enrichment (scheduled)

- **File:** `.github/workflows/ai-enrichment.yml`
- **Schedule:** `35,45,55 19,1,7,13 * * *` UTC (= **01:05 / 07:05 / 13:05 / 19:05 IST**, ~1h after each scrape slot; +10m/+20m backup ticks)
- **Defaults:** `--limit 50`, `--daily-budget 300`
- **Guard:** `scraper.ai_schedule_guard` — one successful/running tick per slot

## Legacy workflow (manual diagnostic only)

- **File:** `.github/workflows/scrape-and-deploy.yml`
- **Status:** No schedule. `workflow_dispatch` only.
- **Defaults:** `deploy=false`, `confirm_legacy_deploy=false`
- **Deploy requires:** both `deploy=true` **and** `confirm_legacy_deploy=true`
- **Purpose:** capped MSTC-only diagnostic runs via `scraper.run_all` — **never for production**

## Expected production dataset

Full multi-source export:

| Source | Expected count |
|--------|----------------|
| MSTC | ~1,681 |
| eAuction | ~61 |
| GeM Forward | ~74 |
| **Total** | **~1,816** |

Also expect ~12,200 lots across all auctions.

## Last known good full dataset

Recorded before the 2026-07-04 incident:

- **Total auctions:** 1,816
- **Total lots:** ~12,200
- **MSTC:** 1,681
- **eAuction:** 61
- **GeM Forward:** 74

## Incident: 2026-07-04

**What happened:** The legacy workflow `.github/workflows/scrape-and-deploy.yml` ran on its old schedule (`0 2 * * *` UTC) with defaults `sources=mstc`, `limit=300`, `deploy=true`. It overwrote production with a **300-record MSTC-only** export.

**Impact:** Live site dropped from 1,816 multi-source auctions to 300 MSTC-only records. GeM Forward and eAuction listings disappeared from the public site.

**Root cause:** Legacy workflow had scheduled deploy enabled with unsafe defaults and no multi-source safety gates.

## Recovery steps

1. Confirm local full dataset in `web/public/data/auctions.json`:
   - count = 1816
   - by_source: mstc 1681, eauction 61, gem_forward 74
2. Rebuild static export:
   ```bash
   cd web
   pnpm run build:prod
   pnpm run verify-build
   ```
3. Deploy `web/out/` only:
   ```bash
   PYTHONPATH=. python3 -m scraper.deploy
   ```
4. Verify live HTTP and parse `auctions-data.js` for correct count and by_source.
5. Confirm legacy workflow schedule is removed and safety gates are in place before trusting automation again.

## Rules

1. **Never deploy capped MSTC-only data to production** (≤500 records, mstc-only).
2. **Never schedule the legacy workflow.**
3. Production deploys must pass safety gates including multi-source checks.
4. A candidate with only one source must not replace production that had multiple sources.
5. Count drops >40% from production require explicit `--allow-large-drop`.
