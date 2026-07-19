# 4-stage pipeline runbook

> **2026-07 update:** Primary production path is **six independent GHA lanes**
> (Discover-MSTC, Discover-GeM, Download-MSTC, Download-GeM, Parse Assets, Build Deploy).
> See [`PIPELINE_DATA_MODEL.md`](PIPELINE_DATA_MODEL.md). Legacy Discover/Download/Drain
> workflows are **manual emergency only**. AI enricher is **held**.

## Production flow (independent lanes)

1. **Discover-MSTC** / **Discover-GeM** — every ~6h, each own concurrency group. Cap 2000. Writes Hostinger snapshots only (no site publish).
2. **Download-MSTC** / **Download-GeM** — every ~6h + self-resume. 5s pause after each success. Item-level ledger checkpoints.
3. **Parse Assets** — every ~2h + self-resume. One auction at a time → `parsed/{source}/{id}.json`.
4. **Build Deploy** — every ~2h. Merge discovery + parse cache → one site deploy. Material search needs lots.

Lanes do **not** wait for each other. Telegram: `SAI · {Lane}` short reports.

### Migrate ledger

```bash
PYTHONPATH=. python -m scraper.pipeline_schema_migrate --pull --push
```

### Cap-2 smoke (critical path)

Optional `workflow_dispatch` inputs (`max_download` / `max_parse` / `auction_ids`) default empty = production uncapped. Smoke does **not** change cron.

```bash
# 1) MSTC download ×2 (+ ledger migrate once)
gh workflow run pipeline-download-mstc.yml -f max_download=2 -f migrate_ledger=true
# From run logs: attempted_ids=ID1,ID2

# 2) GeM download ×2
gh workflow run pipeline-download-gem.yml -f max_download=2
# From run logs: attempted_ids=ID3,ID4

# 3) Parse only those IDs
gh workflow run pipeline-parse-assets.yml -f max_parse=4 -f auction_ids=ID1,ID2,ID3,ID4

# 4) Full site build/deploy (no per-auction cap)
gh workflow run pipeline-build-deploy.yml
```

After smoke: omit caps on future dispatches; scheduled lanes stay uncapped.

## Legacy emergency

```bash
gh workflow run pipeline-discover.yml
gh workflow run pipeline-download.yml -f source=mstc
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
```

---

## Aged-out closing dates

## Fast retries

If **Discover** hard-fails: `pipeline-discover-retry.yml` (+15m / +45m, max 2/slot).

If **Download** hard-fails:

1. Same job retries once (~2 min).
2. `pipeline-download-retry.yml` schedules auto re-dispatch at **+15 min** then **+45 min** (max **2** per 6h slot).
3. Only then wait for the next scheduled 6h discover.

Telegram: `discover_retry_*`, `download_retry_scheduled`, `download_retries_exhausted`.

## Aged-out closing dates

Discovery already filters to `tomorrow` (IST). **Materialize used to reuse yesterday’s production rows verbatim**, so after midnight those rows poison QA (`closes before …`) and stop drain on the same IDs every retry.

Pipeline now:

1. Materialize excludes aged-out / quarantined keys when `min_closing_date` is set.
2. `export_hygiene.strip_aged_out_auctions` runs after materialize (parse + legacy refresh).
3. Poison guard: dropping more than `max(50, 5% of export)` hard-fails (wrong filter) unless ops override.
4. Ledger `parse=done` is marked **only after** safety gates pass.

Count / missing-source / schema failures still hard-stop.

## Record-level DLQ (poison basket)

One bad auction must not stop drain. Tiered integrity:

| Tier | Examples | Behavior |
|------|----------|----------|
| Site-threatening | Missing MSTC, count floor, schema | Hard stop |
| Auto-repairable | Absolute `/pdfs/`, `/docs/`, `/thumbs/` | Rewrite to relative; re-QA |
| Record-poison | Residual absolute paths, stubborn IDs | Quarantine key 48h, strip, continue |
| Ops noise | Aged-out closings, empty eAuction | Strip / warn-only |

Quarantined keys are marked ledger `failed` (not `done`). Replay later:

```bash
python -m scraper.quarantine_tool list
python -m scraper.quarantine_tool remove --key mstc:591395
# then reset that ledger item to parse=pending if needed, and re-run drain
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
```

Deploy live HTTP verify never crashes on spaced thumb URLs (invalid samples → warning).

### Quarantine escape hatch

Stubborn single IDs can be skipped via Hostinger:

`{domain}/auction_pipeline/auction_quarantine.json`

```bash
# Add (default TTL 48h; max 7d)
python -m scraper.quarantine_tool add --key mstc:588636 --reason operator_skip --hours 48 --error-class absolute_path

python -m scraper.quarantine_tool list
python -m scraper.quarantine_tool remove --key mstc:588636
```

Auto-quarantine: residual record-poison after repair/strip is quarantined **48h** (Telegram: `Quarantine added` / parked N bad items). Quarantine cannot take the export below `min_count`.

### Recovery after poison drain stop

Deploy the DLQ fix, then resume (no re-download needed):

```bash
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
```

## Drain failure

- Parse fails ×3 → no deploy → `drain_stopped`
- Deploy fails ×3 → no next parse batch → `drain_stopped`
- Fix root cause, then:

```bash
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
```

## Durable state (Hostinger)

- `{domain}/auction_pipeline/pipeline_ledger.json`
- `{domain}/auction_pipeline/raw/{source}/{id}.html`
- `{domain}/auction_pipeline/download_retry_state.json`
- `{domain}/auction_pipeline/last_deploy.json`
- `{domain}/auction_pipeline/auction_quarantine.json`
- `{domain}/ai_enrichment_state/cache.tar.gz` — durable AI enrichment cache for deploy hydration
- `{domain}/ai_enrichment_state/_daily_usage.json` — OpenRouter daily budget ledger
- Public: `…/public_html/auctions/{pdfs,docs,thumbs,data}`

## AI enrichment on live site

Scheduled `ai-enrichment.yml` writes ready/rejected payloads into `data/ai_enrichment_cache`, pushes `cache.tar.gz` to Hostinger, and updates the done-registry ledger.

Every deploy path now:

1. Restores the GHA AI cache (when present).
2. Pulls `cache.tar.gz` from Hostinger (best-effort).
3. Merges cached AI into `web/public/data/auctions.json` before `build:prod` (`finalize_public_export` also hydrates).

Force a republish after AI cache changes without a parse batch:

```bash
gh workflow run pipeline-deploy.yml -f deploy=true -f force=true
```

## UI / design verify (before force-deploy)

`verify-airbnb-design.mjs` is a **source-only** gate (no `next build`). It runs:

1. Early via `pnpm run verify-deploy-prereqs` (GHA, before expensive build)
2. Again inside `pnpm run verify-build` after build

Before any nav/route/chrome edit + force deploy:

```bash
cd web && pnpm run verify-design
```

Deploy-failed Telegram messages prefer extracted `FAIL …` lines instead of the OK tail of verify-build output.
Pipeline Telegram copy is plain language (e.g. “Nothing new to download”, “waiting to process N”, “Catch-up finished”).

## GeM / eAuction

No raw HTML download stage. Discovery during download marks them parse-ready; drain parse live-enriches in batches; deploy publishes with MSTC.

**Empty eAuction after midnight is warn-only.** When there are no future-closing eAuction rows, parse may still promote (with source fallback for any still-valid previous rows). Deploy predeploy, sitemap, and launch-readiness must **not** hard-fail on zero eAuction — only MSTC is required. Drain continues.

## Detail 404 / shallow JSON / empty crawler search (class failures)

Do **not** hand-edit Hostinger HTML for a missing auction URL.

1. **Detail 404 for a known portal id** — check ledger status → download + drain until backlog clear → full `build:prod` deploy only. Listing data and detail HTML must ship together (parse must not rsync `auctions.json` alone).
2. **Shallow `/api/auction/...json`** (`lots: []`, `enrichment_status: listing_only`) — expected until deep scrape; queue prioritizes incomplete + high-value keywords. After deep parse + deploy, API must match detail lot count.
3. **Crawler sees only “Loading auctions…”** — use dedicated HTML landings (`/aluminium-scrap/`, `/metal-scrap/`, `/large-scrap-lots/`, `/closing-soon/`) or `api/search-index.json` / `api/search/{topic}.json`. There is no dynamic `?q=` search API on static hosting.
4. **Deploy gate** — never deploy until `pnpm run build:prod && pnpm run verify-build` is green, including `verify-crawlable-landings` (raw HTML auction content on aluminium, metal-scrap, large-lots, closing-soon).

## Lot documents / photos media sync

Parse downloads lot photos into `web/public/{docs,thumbs}` and **must** `push_public_media` before promoting `auctions.json`. Deploy also safety-net pushes media after bootstrap.

`finalize_public_export` / promote scrub orphan `lot.documents[].cached_url` / `thumbnail_url` (status → `pending_cache`) so JSON never claims files that are not on disk.

Gates:

| Env | Default | Meaning |
|-----|---------|---------|
| `MEDIA_PUSH_REQUIRED` | `1` | Parse refuses promote if media push fails |
| `PREDEPLOY_DOCS_MODE` | `warn` | Missing lot.documents files warn; set `fail` after backfill |

### Broken photos playbook (e.g. 589631)

1. Local hydrate (no Hostinger):  
   `PYTHONPATH=. python -m scraper.media_backfill --auction-id 589631 --max-docs 50 --no-push`
2. After operator says **deploy12** only:  
   `gh workflow run pipeline-media-backfill.yml -f auction_ids=589631 -f max_docs=500 -f push_media=true`  
   then `gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=2` (or force deploy).
3. Verify live:  
   `curl -sI https://scrapauctionindia.com/auctions/docs/589631/Photo_….pdf` → 200  
   Listing page shows thumbs; no “Bid on MSTC” CTAs.

### UI contract

- Listing page (`/auctions/` cards + table): show local cached photos only.
- No outbound “Bid on MSTC / View on {source}” CTAs anywhere in the UI.
- Local `Open PDF` / cached `/auctions/docs/*` links remain.

## Manual triggers

```bash
gh workflow run pipeline-discover.yml -f queue_cap=2000
gh workflow run pipeline-download.yml -f batch_size=25 -f max_batches=80
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
gh workflow run pipeline-parse.yml -f max_parse=100
gh workflow run pipeline-deploy.yml -f deploy=true -f force=true
# Only after deploy12 approval:
gh workflow run pipeline-media-backfill.yml -f auction_ids=589631 -f max_docs=500
```

## Locks

- `work/discover.lock`, `work/download.lock`, `work/parse.lock`, `work/deploy.lock`, `work/drain.lock`
- GHA concurrency `auction-pipeline-serial` serializes discover ↔ download ↔ drain SSH.
