# MSTC Auction Listings

A lightweight, searchable listing site for [MSTC](https://www.mstcindia.co.in) e-auctions.  
No VPS. No Google Sheets. Static site on Hostinger.

**Current scope:** MSTC + GeM Forward + eAuction unified pipeline. Live site: https://lightcyan-camel-979846.hostingersite.com/auctions/ (automated daily refresh via GitHub Actions).

Live site: https://lightcyan-camel-979846.hostingersite.com/auctions/

## What it does

- **Scraper** (`scraper/`): Fetches MSTC listing API, enriches with HTML detail pages and PDF catalogues, applies 20-day retention, writes `web/public/data/auctions.json`.
- **Website** (`web/`): Next.js static export — search, filters, date filters (IST), pagination, expandable lots with full four-section catalogue text.

Each lot preserves **structured fields** plus raw PDF sections:

- `lot_details_text`
- `lot_description_text`
- `lot_parameters_text`
- `lot_documents_text`

## Project structure

```
mstc-auction-listings/
├── scraper/          # Python pipeline
├── web/              # Next.js frontend (pnpm)
├── tests/
├── .github/workflows/
├── requirements.txt
└── .env.example
```

## Local setup

### Python scraper

```bash
cd mstc-auction-listings
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional for deploy keys
```

### Scrape commands

QA stratified scrape (3 auctions per office — for testing):

```bash
PYTHONPATH=. python -m scraper.main \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs \
  --limit-per-office 3
```

Targeted office QA (example):

```bash
PYTHONPATH=. python -m scraper.main \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs \
  --office JPR \
  --limit 5
```

Capped production scrape via orchestrator (recommended):

```bash
PYTHONPATH=. python -m scraper.run_all \
  --sources mstc \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --limit 300 \
  --max-docs-per-run 100
```

Legacy MSTC-only entry point (still supported):

```bash
PYTHONPATH=. python -m scraper.main \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --limit 300 \
  --max-docs-per-run 100
```

Full production scrape (all retained auctions):

```bash
PYTHONPATH=. python -m scraper.main \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs
```

QA summary after scrape:

```bash
PYTHONPATH=. python -m scraper.qa_summary --json web/public/data/auctions.json
PYTHONPATH=. python -m scraper.qa_summary --json web/public/data/auctions.json --fail-on-threshold
```

Document cache (lot annexure/photo attachments):

```bash
PYTHONPATH=. python -m scraper.main \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --auction-id 587164 \
  --max-docs-per-run 10
```

Cached files live under `web/public/docs/{auction_id}/` and thumbnails under `web/public/thumbs/{auction_id}/{lot_id}/`.

Continue document caching without a full MSTC rescrape:

```bash
PYTHONPATH=. python -m scraper.hydrate_documents \
  --json web/public/data/auctions.json \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --max-docs-per-run 200
```

Hydration also refreshes item-wise EMD status/summary on existing JSON.

Stale document cleanup (manual only):

```bash
PYTHONPATH=. python -m scraper.document_retention \
  --json web/public/data/auctions.json \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --dry-run

# Apply deletions only after reviewing dry-run output:
PYTHONPATH=. python -m scraper.document_retention \
  --json web/public/data/auctions.json \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --apply
```

Optional sources:

```bash
# GeM Forward (requires India IP or SSH transport)
PYTHONPATH=. python -m scraper.gem_forward_scraper --limit 10 --listing-only

# eAuction.gov.in public probe (Closing By Date tabs — no captcha on default tabs)
PYTHONPATH=. python -m scraper.eauction_probe --out work/eauction_probe.json --tab closingWeekTab

# eAuction is captcha-protected only on Advanced Search / Closing By Date custom search.
# Public path: FrontEndEauctionByDate with closingTodayTab / closingWeekTab / closingTwoWeekTab.

# Multi-source orchestrator
PYTHONPATH=. python -m scraper.run_all --sources mstc,eauction,gem_forward --limit 50
```

### Frontend (pnpm only)

```bash
cd web
pnpm install
pnpm dev              # http://localhost:3000
pnpm run build:prod   # static export to web/out/ (basePath /auctions)
pnpm run verify-build
```

## Data sources

| Source | URL | Provides |
|--------|-----|----------|
| Listing API | `/mstcwebservice/Service.svc/getScrollMsg/{office}` | Discovery, dates, lot flags |
| HTML detail | `/TenderEntry/Lot_Item_Details_AucID.aspx?ARID={id}` | Items, location, contact |
| PDF catalogue | POST `auction_detailed_report_pdf.jsp` | Lot sections, prices, EMD |

## Deployment

Deployment uses **SSH key authentication only**. The static export in `web/out/` is synced to Hostinger via `scraper/deploy.py` (rsync over SSH).

Target: `/home/u268110164/domains/lightcyan-camel-979846.hostingersite.com/public_html/auctions`

### Local deployment

```bash
export HOSTINGER_HOST=82.25.107.163
export HOSTINGER_PORT=65002
export HOSTINGER_USERNAME=u268110164
export HOSTINGER_SSH_KEY=~/.ssh/cursor_mstc_auction_hostinger
export HOSTINGER_REMOTE_DIR=/home/u268110164/domains/lightcyan-camel-979846.hostingersite.com/public_html/auctions

PYTHONPATH=. python -m scraper.run_all \
  --sources mstc \
  --out web/public/data/auctions.json \
  --pdf-dir web/public/pdfs \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --limit 300 \
  --max-docs-per-run 200
PYTHONPATH=. python -m scraper.hydrate_documents --json web/public/data/auctions.json --max-docs-per-run 200
PYTHONPATH=. python -m scraper.qa_summary --json web/public/data/auctions.json
cd web && pnpm run build:prod && pnpm run verify-build && cd ..
python -m scraper.deploy
```

## Automated daily refresh

Production updates use a guarded pipeline that prefers **stale-good data over fresh-bad data**. A failed scrape never deploys.

### One-command refresh

```bash
# Dry run (scrape + merge + QA + promote + build — no deploy)
PYTHONPATH=. python -m scraper.refresh_and_deploy --no-deploy

# Full production refresh with deploy
PYTHONPATH=. python -m scraper.refresh_and_deploy \
  --sources mstc,gem_forward,eauction \
  --max-docs-per-run 2000 \
  --min-count 1000 \
  --deploy
```

`min_closing_date` is computed automatically as **tomorrow in IST** (future-only filter).

Each run writes artifacts under `work/runs/{run_id}/` (batches, logs, `reports/final_report.md/json`) and updates `work/runs/latest.json`.

### Safety gates (hard fail → no promote / no deploy)

- Candidate count ≥ `--min-count` (default 1000)
- No accidental 1-record export
- Total count must not drop >40% vs production (unless `--allow-large-drop`)
- MSTC count must not drop >40% vs production
- Earliest closing ≥ tomorrow IST
- Required sources: MSTC + eAuction (use `--warn-missing-eauction` for warn-only)
- GeM missing is warn-only
- No failed MSTC office batches (unless `--allow-failed-batches`)
- HTML/PDF failure rates under 5%
- JSON schema valid (Pydantic)
- `verify-build` must pass before deploy

### Locking

Overlapping runs are blocked via `work/refresh.lock`. Use `--break-stale-lock` if a prior run crashed.

### Status and rollback

```bash
PYTHONPATH=. python -m scraper.status_report
PYTHONPATH=. python -m scraper.status_report --check-live

PYTHONPATH=. python -m scraper.rollback_deploy --list
PYTHONPATH=. python -m scraper.rollback_deploy \
  --backup work/backups/auctions_YYYYMMDD_HHMMSS.json \
  --deploy
```

### GitHub Actions (recommended primary scheduler)

Workflow: `.github/workflows/refresh-and-deploy.yml`

- **Schedule:** daily at 01:30 IST (20:00 UTC previous day)
- **Manual:** Actions → Refresh and Deploy → Run workflow
- **Uses pnpm only** (`pnpm install --frozen-lockfile` with fallback)
- Uploads `work/runs/*/reports/` and logs as artifacts
- On failure, uploads run diagnostics

Required repository secrets:

| Secret | Description |
|--------|-------------|
| `HOSTINGER_HOST` | SSH host |
| `HOSTINGER_PORT` | SSH port (`65002`) |
| `HOSTINGER_USERNAME` | SSH username |
| `HOSTINGER_SSH_KEY` | Private key **contents** (not a path) |
| `HOSTINGER_REMOTE_DIR` | Remote deploy path (`.../public_html/auctions`) |
| `SITE_BASE_URL` | e.g. `https://lightcyan-camel-979846.hostingersite.com/auctions` |
| `OPENROUTER_API_KEY` | Optional AI fallback |
| `OPENROUTER_MODEL` | Optional |
| `OPENROUTER_FALLBACK_MODELS` | Optional |

**Failure behavior:** live site remains on the last successful deploy. Failed runs write `work/runs/{run_id}/reports/final_report.md` with errors.

**Hostinger cron:** not recommended for this pipeline (scraping + build needs ~2 hours and Python/Node tooling). Use GitHub Actions instead.

### Legacy manual deployment

See batch pipeline commands above (`batch_run`, `merge_batches`, `qa_summary`, `promote_export`, `deploy`).

### Security

- Do not commit private keys or `.env` files (only `.env.example` is tracked).
- Deployment logs never print secrets.
- Locally `HOSTINGER_SSH_KEY` is a **file path**. In GitHub Actions, `HOSTINGER_SSH_KEY` is the **full private key text**.
- Store `HOSTINGER_SSH_KEY` (private key) and `OPENROUTER_API_KEY` only in GitHub Actions secrets or local environment variables — never in the repo.
- The public deploy key (`.github/hostinger_deploy_key.pub`) is safe to commit.
- Keys used during initial setup should be rotated after deployment verification.

## Tests

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

## Multi-source schema

`AuctionRecord` includes unified fields while keeping MSTC IDs unchanged:

- `source` (`mstc` | `eauction` | `gem_forward`)
- `source_auction_id`
- `detail_url`, `document_urls`
- `asset_category` (vehicle, scrap, machinery, ewaste, minerals, timber, property, coal, other)
- `platform`, `state`

## AI fallback (optional)

Set `OPENROUTER_API_KEY` to enable low-confidence extraction via `scraper/ai_extractor.py`.  
AI is never called in tests and does not overwrite high-confidence parser values.

## Known limitations

- **eAuction.gov.in** public listing works via `FrontEndEauctionByDate` closing-date tabs (no captcha). Captcha applies only to Advanced Search / custom date search. Detail pages (`component=view`) are accessible without login.
- **GeM Forward** works via direct transport from some networks; use `--transport ssh` on Hostinger if blocked.
- **OpenRouter** is optional; set `OPENROUTER_API_KEY` for low-confidence extraction smoke tests only.
- Document download budget (`--max-docs-per-run`) caps new downloads per run; use `hydrate_documents` to continue.
- Some MSTC annexures return 173-byte HTML error pages (`too_small`); these are preserved as failed with reason.
- Stale document cleanup is manual only (`scraper.document_retention`).

## License

Private / internal use. MSTC data remains subject to MSTC terms of use.
