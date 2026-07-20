# Pipeline runbook (v3 — mandatory PDF/doc)

> **Law:** No MSTC/GeM listing goes live without CDN PDF/doc **and** parse with lots.
> Six GHA lanes: Discover-MSTC/GeM, Download-MSTC/GeM, Parse, Build-Deploy.
> Media SoR: R2 (`files.csmg.in`). Schema: [`PIPELINE_DATA_MODEL.md`](PIPELINE_DATA_MODEL.md). AI enricher **held**.

## Steady-state schedules (set-and-forget)

All crons are **UTC**. IST = UTC+5:30. Schedules live on the **default branch** only.

| Lane | Cron (UTC) | IST (approx) | Interval | Cap / batch | Timeout | Concurrency |
|------|------------|--------------|----------|-------------|---------|-------------|
| Discover MSTC | `17 */3 * * *` | :47 | 3h | queue_cap **500** | 90m | `pipeline-discover-mstc` |
| Discover GeM | `23 */3 * * *` | :53 | 3h | queue_cap **500** | 90m | `pipeline-discover-gem` |
| Download MSTC | `41 * * * *` | :11 | 1h | max **150**; wave 25; workers 4; max-batches 20 | 120m / step 90m | `pipeline-download-mstc` |
| Download GeM | `47 * * * *` | :17 | 1h | max **100**; wave 25; workers 3 | 120m / step 90m | `pipeline-download-gem` |
| Parse Assets | `11 * * * *` | :41 | 1h | max_parse **200**; wave 100; workers 2 | 120m | `pipeline-parse-assets` |
| Build Deploy | `19 */2 * * *` | :49 | 2h | normal export (no scheduled `allow_small`) | 180m | `pipeline-build-deploy` |
| Publish Media | *(none)* | — | manual | wave 50 | 60m | `pipeline-publish-media` |

Shared rules:

- Writers use `cancel-in-progress: false`.
- Closing floor: `MIN_CLOSING_HOURS_AHEAD=12` (closing ≥ now+12h IST).
- Download: `MEDIA_R2_ONLY=1`, `DOWNLOAD_DECOUPLE_FLUSH=0` (R2 flush failure → fail item; next hour retries).
- Prefer odd cron minutes (avoid :00/:15/:30 GHA congestion).
- Manual `workflow_dispatch` still accepts higher caps for smoke/drain.

### Drain mode (temporary backlog)

If download eligible backlog grows for ~48h, temporarily bump cadence/caps, then revert to the table above. Example drain snippets (do **not** leave permanently):

```yaml
# Discover: every 2h, queue_cap 2000
# Download MSTC: "5,35 * * * *", max_download 2000, max-batches 80
# Parse: "10,40 * * * *", max_parse empty/unbounded under timebox
# Build: "7,22,37,52 * * * *" + allow_small only while cutover
```

### Cutover / small export

Scheduled Build Deploy does **not** pass `--allow-small-export`. For empty→first fill only:

```bash
gh workflow run pipeline-build-deploy.yml -f allow_small_export=true
```

## Production flow

1. **Discover** — require `portal_doc_url`; snapshot only; upsert ledger
2. **Download** — portal → R2 CDN; `download=done` before parse
3. **Parse** — R2 prefetch; `lots_count > 0` for publishable
4. **Build-Deploy** — export **only** publishable future-closing rows

### Cutover (unpublish shells + ledger v3)

```bash
gh workflow run pipeline-build-deploy.yml \
  -f migrate_ledger_v3=true \
  -f allow_small_export=true
```

Then drain with Download → Parse → Build (cron or manual caps).

### Migrate ledger only

```bash
PYTHONPATH=. python -m scraper.pipeline_schema_migrate --pull --push
```

### Cap-2 smoke

```bash
gh workflow run pipeline-download-mstc.yml -f max_download=2
gh workflow run pipeline-download-gem.yml -f max_download=2
gh workflow run pipeline-parse-assets.yml -f max_parse=4
gh workflow run pipeline-build-deploy.yml -f allow_small_export=true
```

## Legacy emergency

```bash
gh workflow run pipeline-discover.yml
gh workflow run pipeline-download.yml -f source=mstc
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
```

---

## Fast retries

If **Discover** hard-fails: `pipeline-discover-retry.yml` (+15m / +45m, max 2/slot).

If **Download** hard-fails:

1. Same job retries once (~2 min).
2. `pipeline-download-retry.yml` schedules auto re-dispatch at **+15 min** then **+45 min** (max **2** per 6h slot).
3. Only then wait for the next scheduled discover.

Telegram: retries send **action** / **critical** cards (Needs attention / FAILED) via `send_action_card` — lane card only, no legacy event spam.

## Aged-out closing dates

Discovery and download use **min runway** `closing >= now + 12h` (IST), env `MIN_CLOSING_HOURS_AHEAD`. CLI `--min-closing-date YYYY-MM-DD` still overrides for ops/tests.

Pipeline now:

1. Materialize excludes aged-out / quarantined keys when min closing is set.
2. `export_hygiene.strip_aged_out_auctions` runs after materialize (parse + legacy refresh); missing closing is dropped.
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

Auto-quarantine: residual record-poison after repair/strip is quarantined **48h** (ops JSON / run reports; not a Telegram progress ping). Quarantine cannot take the export below `min_count`.

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

## Telegram ops cards

One HTML card protocol (`scraper/telegram_reporter.py`). **Lane card only** — no emoji-event dual reporting.

| Severity | When | Suppressible? |
|----------|------|-----------------|
| `silent` | credentials missing, true noop, zero delta, AI held | n/a (no send) |
| `progress` | lane finished with meaningful delta | quiet hours + 10m dedupe |
| `digest` | daily catalogue summary (cron `7 3 * * *` UTC ≈ 08:37 IST) | never |
| `action` | retries exhausted, high fail ratio | never |
| `critical` | site promote fail, pipeline silent / deadman | never |

Typography (HTML): **Title** → outcome → `metrics · metrics` → soft context → optional `Open run`.

Lane display names: Discover MSTC/GeM · Download MSTC/GeM · Process catalogues · Update site · Upload media.

Env:

| Env | Default | Meaning |
|-----|---------|---------|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | required to send |
| `TELEGRAM_NOOP_SILENT` | `1` | noop lanes stay silent (`0` to debug) |
| `TELEGRAM_QUIET_HOURS_IST` | unset | e.g. `23-07` suppresses **progress** only |

Examples:

```
<b>Discover MSTC</b>
Found 2,192 live · 480 new · 500 queued
Still need files: 1,820 · Ready to process: 140

<b>Update site</b>
FAILED — promote refused
<code>count floor not met</code>
<a href="…">Open run</a>

<b>Daily catalogue</b>
20 Jul · 09:00 IST
Live on site: 375 · Ready for site: 40 · Still need files: 120
Yesterday: +180 downloaded · +160 processed · 3 failed
All clear
```

Manual ping: workflow `telegram-status.yml` → `send_ops_note`. Daily: `scripts/telegram_daily_digest.py` / `telegram-daily-digest.yml`.

Deploy-failed cards prefer extracted `FAIL …` lines (via verify-fail extract) clipped into `<code>`, not the OK tail of verify-build.

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
