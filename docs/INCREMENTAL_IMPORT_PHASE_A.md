# Incremental Import Phases A-B

Phase A adds the first production-grade layer for importing only what needs work: deterministic listing snapshots and change decisions.

## What Exists Now

The scraper can compare a current candidate export against a previous production export and classify every auction as:

1. `new` — not seen before.
2. `unchanged` — listing-level fingerprint is identical and the old record is healthy.
3. `changed` — source-visible listing fields changed, so deep parsing should run again.
4. `needs_repair` — listing is unchanged, but the old enriched record is incomplete or low confidence.
5. `removed` — present in the previous export but absent from current discovery.

## Fingerprint Inputs

The listing hash intentionally uses stable source-visible fields, not display-only UI data:

- Source and source auction ID
- Auction number
- Item summary
- Seller
- Location and state
- Opening, closing, and listed date
- Detail URL
- PDF URL
- Document URLs
- Lot count
- First 25 lot signatures: lot ID, title, quantity, unit, start price, document filenames
- Price parse status
- EMD parse status

## Repair Detection

An unchanged auction is still rework-worthy when the previous record has signs of bad enrichment:

- `status` is `failed`, `partial`, or `listing_only`
- `parse_confidence` is `low` or `minimal`
- lots are missing
- errors are present
- `missing_fields` contains `lots`
- price is explicitly missing and `start_price` is missing

## CLI

```bash
PYTHONPATH=. python3 -m scraper.incremental \
  --current web/public/data/auctions.json \
  --previous web/public/data/auctions.json \
  --out work/incremental_report.json
```

The report is JSON and includes counts, per-auction decisions, reasons, and current snapshots.

## What Phase A Does Not Do Yet

Phase A does not skip network work inside the crawlers. It creates the reliable decision layer first. The next phase can safely wire these decisions into the runner:

- Run shallow discovery for all sources.
- Compare against the last production export.
- Deep-parse only `new`, `changed`, and `needs_repair`.
- Reuse existing enriched records for `unchanged`.
- Mark `removed` without losing history.

This avoids the dangerous version of incremental import where we skip records without a clear reason trail.

## Phase B: Reuse Healthy Unchanged Records

Phase B adds the first real reuse mechanism. Given a current candidate export and a previous production export, it produces a merged export where:

- `unchanged` records are copied from the previous enriched export.
- `new`, `changed`, and `needs_repair` records remain from the current candidate export.
- `removed` records are not included in the current export, but are counted in the report.
- Candidate order and membership remain authoritative.

This preserves expensive fields for unchanged auctions:

- PDF/lot parsing results
- document and thumbnail metadata
- import dates
- display enrichment
- AI headings/tags/summaries
- any future buyer-facing enrichment

### Standalone Reuse CLI

```bash
PYTHONPATH=. python3 -m scraper.incremental \
  --current work/future_full_auctions.json \
  --previous web/public/data/auctions.json \
  --out work/incremental_report.json \
  --merged-out work/future_full_auctions_reused.json
```

### Batch Merge Integration

`merge_batches` can now opt into the same reuse layer:

```bash
PYTHONPATH=. python3 -m scraper.merge_batches \
  --batch-dir work/batches \
  --out work/future_full_auctions.json \
  --min-closing-date 2026-07-11 \
  --previous-export web/public/data/auctions.json \
  --reuse-unchanged \
  --incremental-report work/incremental_report.json
```

## Still Not Done

Phase B still does not prevent network calls before parsing. It safely reuses enriched output after a candidate export exists. The next phase should add shallow discovery manifests so the runner can skip deep parsing before spending PDF/document/AI work.

## Phase C: Shallow Discovery And Deep-Work Plan

Phase C adds the planning layer that runs before expensive parsing.

### Shallow Discovery

`scraper.discovery` fetches only source-visible listing data:

- MSTC listing API records, without HTML/PDF catalogue parsing.
- GeM Forward listing records, without detail/rules enrichment.
- eAuction ByDate listing rows, without detail page enrichment.

It writes a normal `AuctionsExport` with `stats.discovery_only = true`.

```bash
PYTHONPATH=. python3 -m scraper.discovery \
  --sources mstc,gem_forward,eauction \
  --min-closing-date 2026-07-11 \
  --out work/discovery_latest.json
```

### Work Plan

`scraper.incremental_plan` compares shallow discovery against the previous production export using `listing` scope. This avoids treating missing PDF/lot data in discovery as a source change.

```bash
PYTHONPATH=. python3 -m scraper.incremental_plan \
  --discovery work/discovery_latest.json \
  --previous web/public/data/auctions.json \
  --out work/incremental_work_plan.json \
  --ids-dir work/incremental_ids
```

The plan maps decisions to work actions:

- `unchanged` -> `reuse_previous`
- `new` -> `deep_parse`
- `changed` -> `deep_parse`
- `needs_repair` -> `deep_parse`
- `removed` -> `mark_removed`

`--ids-dir` writes machine-readable ID lists such as:

- `deep_parse_mstc.json`
- `reuse_previous_mstc.json`
- `mark_removed_gem_forward.json`

This is the first point where the system can know, before parsing, exactly where expensive work should be spent.

## Still Not Done After Phase C

The runners do not yet consume the Phase C ID lists to skip deep parsing automatically. Phase D should wire `deep_parse_*.json` into MSTC/GeM/eAuction batch execution and reuse previous records for `reuse_previous` without calling PDF/detail/AI paths.

## Phase D: Work-Plan Execution And Materialization

Phase D wires the plan into the runner.

### Deep-Parse Only What The Plan Requires

`batch_run` accepts a work plan:

```bash
PYTHONPATH=. python3 -m scraper.batch_run \
  --sources mstc,gem_forward,eauction \
  --min-closing-date 2026-07-11 \
  --batch-dir work/batches \
  --pdf-dir web/public/pdfs \
  --docs-dir web/public/docs \
  --thumbs-dir web/public/thumbs \
  --max-docs-per-run 2000 \
  --work-plan work/incremental_work_plan.json
```

With a work plan:

- MSTC deep-parses only `deep_parse` auction IDs.
- MSTC also uses office metadata from discovery, so offices with no deep-parse IDs are skipped.
- GeM Forward enriches only `deep_parse` auction IDs.
- eAuction fetches details only for `deep_parse` auction IDs.
- Sources with zero deep-parse IDs write empty batch exports without wasting detail/PDF work.

### Merge Deep-Parsed Records

```bash
PYTHONPATH=. python3 -m scraper.merge_batches \
  --batch-dir work/batches \
  --out work/parsed_deep.json \
  --min-closing-date 2026-07-11
```

### Materialize Complete Export

`scraper.incremental_materialize` combines the plan, previous export, and parsed-deep export:

```bash
PYTHONPATH=. python3 -m scraper.incremental_materialize \
  --work-plan work/incremental_work_plan.json \
  --previous web/public/data/auctions.json \
  --parsed work/parsed_deep.json \
  --out work/future_full_auctions.json
```

Materialization rules:

- `reuse_previous` -> copy previous enriched record.
- `deep_parse` -> use parsed-deep record.
- `mark_removed` -> omit from current export.
- Missing deep-parse records fail the run by default.

### Phase D Smoke Result

A live MSTC HO smoke produced:

- Discovery: 3 HO records.
- Work plan: 1 `deep_parse`, 2 `reuse_previous`.
- Batch execution: only `mstc_HO` ran.
- Parsed-deep export: 1 record.
- Materialized export: 3 records, with 2 reused from previous export.

This proves the expensive path can now be narrowed before parsing.

## Still Not Done After Phase D

The full `refresh_and_deploy` orchestrator is not yet switched to the incremental sequence. Phase E should replace the current full batch path with:

1. discovery
2. work plan
3. work-plan batch execution
4. merge parsed-deep
5. materialize full export
6. existing QA/promote/build/deploy gates
