# GitHub Actions artifacts guide

Use this when reviewing the first **Refresh and Deploy** workflow runs.

## Where artifacts appear

After each workflow run, open **Actions → Refresh and Deploy → run → Artifacts**:

| Artifact | Contents |
|----------|----------|
| `refresh-run-<run_id>` | `work/runs/latest.json`, per-run `reports/`, `logs/` |
| `refresh-failure-<run_id>` | Lock file + full `work/runs/` tree (only on failure) |

Inside `work/runs/<run_id>/reports/`:

- **`final_report.md`** — human-readable summary (start here)
- **`final_report.json`** — machine-readable same payload

`work/runs/latest.json` always points at the most recent run metadata.

## Dry run (`deploy=false`)

Expected in `final_report.md`:

- `Status: success`
- **`Deployed: False`**
- `deploy.deployed: false` and `deploy.skipped: true` in JSON
- Counts in the ~1,700–1,900 range (source drift)
- `by_source` includes `mstc`, `gem_forward`, `eauction`
- `min_closing_date` is tomorrow IST or later
- Safety gates passed
- Build + verify-build passed

Live Hostinger site should be **unchanged**.

## Deploy run (`deploy=true`)

Only after a green dry run:

- `Deployed: True`
- `http_verify` section with index/PDF/thumbnail checks
- `live_count_hint` near production count

## Logs

Per-step logs live under `work/runs/<run_id>/logs/` (uploaded in the artifact). Search for `ERROR` or `safety gates` if the run failed.

## Decision checklist: run `deploy=true`?

1. Dry run artifact `final_report.md` is green.
2. `total_auctions` ≥ 1,000 and safety gates passed.
3. `earliest_closing` ≥ tomorrow IST.
4. `document_recovery.too_small` is informational only (does not block).
5. No unexpected source drop vs last successful deploy.
6. You are ready to replace live `/public_html/auctions`.

If any gate fails, **do not deploy** — fix or re-run dry.

## Optional failure notifications

Set repository secret or env `NOTIFY_WEBHOOK_URL` to a generic JSON webhook.  
Failures call `scraper.notify.send_failure_notification`; notification errors never fail the pipeline.

## What we do not run from Cursor

Do not trigger the full 90+ minute scrape locally or from the IDE unless explicitly needed. Use GitHub Actions manual dispatch for operational verification.
