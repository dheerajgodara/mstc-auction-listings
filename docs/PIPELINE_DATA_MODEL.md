# Pipeline data model v3 — mandatory PDF/doc

**Law:** Every MSTC/GeM portal listing has a PDF/doc. Nothing is live without a Hostinger copy **and** successful parse (`lots_count > 0`).

## GeM document URL law

- `eauction-download-document/{id}/{token}` is an **HTML UI shell** (hint only). Never save its body as `docs/gem/{id}.*`.
- Real binaries come from notice → `xcommon/ajax/file-list` → `xcommon/file-download` (or notice PDF).
- `download=done` requires magic `%PDF` / Office `PK` / OLE — never HTML / unknown `.bin`.

## Flow

1. **Discover** — record listing + `portal_doc_url` (required)
2. **Download** — fetch → Hostinger → set `hostinger_doc_url` / `hostinger_doc_path` / `doc_sha256`
3. **Parse** — use Hostinger copy only → `parsed/{source}/{id}.json` with lots
4. **Build-Deploy** — publish **only** `publishable` rows

Six independent GHA lanes (unchanged clocks): Discover-MSTC, Discover-GeM, Download-MSTC, Download-GeM, Parse, Build-Deploy.

## Ledger v3 (`auction_pipeline/pipeline_ledger.json`)

| Field | Required for |
|-------|----------------|
| `schema_version` = 3 | always |
| `portal_doc_url` | discover done → download queue |
| `hostinger_doc_path` + `hostinger_doc_url` | download done → parse |
| `parse=done` + `lots_count>0` | `publishable` |
| `publishable` (computed) | build/deploy inclusion |

Stages: `discover` / `download` / `parse` / `deploy` ∈ `{pending,done,failed,blocked}`.

**Removed from active paths:** `listing_only`, `deep_enrichment_pending`, `media_synced`, `deploy_ready`, `enrichment_status` as publish gates.

## Publish gate

```
publishable =
  download==done
  AND hostinger_doc_url
  AND hostinger_doc_path
  AND parse==done
  AND lots_count > 0
  AND not removed_from_source
  AND source in {mstc, gem_forward}
```

## Migrate / cutover

```bash
PYTHONPATH=. python -m scraper.pipeline_schema_migrate --pull --push
# Then unpublish shells:
gh workflow run pipeline-build-deploy.yml -f allow_small_export=true -f migrate_ledger_v3=true
```

Legacy v2 rows are mapped once; unfinished work is re-queued (download/parse pending). Shells leave the live site until publishable.
