# Production status

## Live site

- **URL:** https://scrapauctionindia.com/auctions/
- **Host:** Hostinger static export at `domains/scrapauctionindia.com/public_html/auctions`
- **Canonical domain only:** `scrapauctionindia.com`. Hostinger preview subdomains are not production and must not receive scheduled auction deploys.

## Production workflow (authoritative) — Download → Drain

| Job | Workflow | Module | Schedule / trigger |
|-----|----------|--------|-------------------|
| **1. Download** | `pipeline-download.yml` | `scraper.pipeline_download` | `30 0,6,12,18 * * *` UTC (= **00/06/12/18 IST**), cap **2000** |
| **1b. Download retry** | `pipeline-download-retry.yml` | `scraper.download_retry_controller` | on Download **failure** (+15m / +45m, max 2/slot) |
| **2. Drain** | `pipeline-drain.yml` | `scraper.pipeline_drain` | after Download **success** + safety `0 */6 * * *` UTC |
| Parse / Deploy | `pipeline-parse.yml` / `pipeline-deploy.yml` | modules | **manual emergency only** |

Drain loop each cycle: **Parse 100 → Deploy** (job retries ×3 each) until parse backlog clear (max 25 cycles).

- **Download:** MSTC-only deep raw/PDF; GeM/eAuction discover → parse live enrich
- **Ledger / markers:** `{domain}/auction_pipeline/{pipeline_ledger,download_retry_state,last_deploy}.json` + `raw/`
- **Safety gates:** on Parse → promote inside drain
- **Concurrency:** `auction-pipeline-serial` (download ↔ drain serialized)
- **Legacy monolith:** `refresh-and-deploy.yml` manual emergency only
- **Ops:** `docs/PIPELINE_RUNBOOK.md`, `docs/PIPELINE_OPS_PLAN.md`

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
