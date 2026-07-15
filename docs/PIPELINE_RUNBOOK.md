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

### Quarantine escape hatch

Stubborn single IDs (clock skew / bad closing parse) can be skipped via Hostinger:

`{domain}/auction_pipeline/auction_quarantine.json`

```bash
# Add (default TTL 48h; max 7d)
python -m scraper.quarantine_tool add --key mstc:588636 --reason operator_skip --hours 48

python -m scraper.quarantine_tool list
python -m scraper.quarantine_tool remove --key mstc:588636
```

Auto-quarantine: if residual aged-out errors remain after strip+re-QA, those IDs are quarantined **48h** and parse continues (Telegram: `Quarantine · added N · 48h`). Quarantine cannot take the export below `min_count`.

### Recovery after aged-out drain stop

Deploy this hygiene fix, then resume (no re-download needed):

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
- Public: `…/public_html/auctions/{pdfs,docs,thumbs,data}`

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
