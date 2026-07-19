# Pipeline data model (six independent lanes)

Hostinger file “DB” + live export. **Never delete** ledger rows, PDFs, raw HTML, parse JSON, or unknown legacy keys.

## Stores

| Store | Path | Owner |
|-------|------|--------|
| Ledger | `auction_pipeline/pipeline_ledger.json` | All lanes (merge-safe patches) |
| Discover MSTC | `auction_pipeline/discovery_mstc_latest.json` | Discover-MSTC |
| Discover GeM | `auction_pipeline/discovery_gem_latest.json` | Discover-GeM |
| Raw HTML | `auction_pipeline/raw/{source}/{id}.html` | Download-* |
| MSTC PDFs | `{auctions}/pdfs/{id}.pdf` | Download-MSTC |
| Parse cache | `auction_pipeline/parsed/{source}/{id}.json` | Parse |
| Live export | `{auctions}/data/auctions.json` | Build-Deploy |

## Lanes (independent clocks)

1. **Discover-MSTC** / **Discover-GeM** — listing APIs → ledger upsert + snapshot. No site publish.
2. **Download-MSTC** / **Download-GeM** — durable assets to Hostinger; 5s pause after each success; item-level checkpoint.
3. **Parse** — one-by-one; write parse JSON; skip if sha256 fresh.
4. **Build-Deploy** — merge discoveries + parse cache → one deploy.

No lane waits on another. Progress survives mid-batch failures (commit after each item).

## Ledger v2 fields (additive)

Identity: `stable_key`, `source`, `source_auction_id`, `closing`, `priority_score`, `first_queued_at`, `discover_seen_at`, `removed_from_source`, `listing_fingerprint`

Stages: `discover`, `download`, `parse`, `build` (+ attempts / `*_last_error`)

Assets: `pdf_path`, `raw_html_path`, `media_synced`, `parsed_path`, `parsed_at`, `pdf_sha256`, `parser_version`

Deploy: `deploy_ready` (legacy), `deployed_at`, `deployed_export_hash`

Migrate: `PYTHONPATH=. python -m scraper.pipeline_schema_migrate --pull --push`

## Export Active vs Legacy

**Active:** identity, assets, `lots[]`, deterministic display, `enrichment_status`, `pipeline{}`

**Legacy inert:** all `ai_*` (preserved; not generated; Build prefers non-AI)

## Telegram

Each lane: `SAI · {Lane}` short finish/fail messages via `send_lane_report`.
