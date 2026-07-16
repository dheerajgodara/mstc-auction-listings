# 3-job + drain pipeline runbook

## Production flow

1. **Download** (`pipeline-download.yml`) — every **6h IST**, cap **2000** MSTC deep downloads (new/changed/needs_repair pending).
2. **Drain** (`pipeline-drain.yml`) — after successful download (and 6h safety sweep): **Parse 100 → Deploy** until parse backlog clear.
3. **Parse / Deploy** workflows — **manual emergency only** (drain owns the loop).

## Fast download retry

If Download hard-fails:

1. Same job retries once (~2 min).
2. `pipeline-download-retry.yml` schedules auto re-dispatch at **+15 min** then **+45 min** (max **2** per 6h slot).
3. Only then wait for the next scheduled 6h download.

Telegram: `download_retry_scheduled`, `download_retries_exhausted`.

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

Auto-quarantine: residual record-poison after repair/strip is quarantined **48h** (Telegram: `Quarantine · added N · absolute_path · 48h`). Quarantine cannot take the export below `min_count`.

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

Deploy-failed Telegram messages now prefer extracted `FAIL …` lines instead of the OK tail of verify-build output.

## GeM / eAuction

No raw HTML download stage. Discovery during download marks them parse-ready; drain parse live-enriches in batches; deploy publishes with MSTC.

**Empty eAuction after midnight is warn-only.** When there are no future-closing eAuction rows, parse may still promote (with source fallback for any still-valid previous rows). Deploy predeploy, sitemap, and launch-readiness must **not** hard-fail on zero eAuction — only MSTC is required. Drain continues.

## Manual triggers

```bash
gh workflow run pipeline-download.yml -f max_download=2000
gh workflow run pipeline-drain.yml -f max_parse=100 -f max_cycles=25
gh workflow run pipeline-parse.yml -f max_parse=100
gh workflow run pipeline-deploy.yml -f deploy=true -f force=true
```

## Locks

- `work/download.lock`, `work/parse.lock`, `work/deploy.lock`, `work/drain.lock`
- GHA concurrency `auction-pipeline-serial` serializes download ↔ drain SSH.
