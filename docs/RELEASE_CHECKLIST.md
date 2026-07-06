# Release Checklist

Use this checklist before promoting a candidate export to production (Hostinger).

## Pre-merge

- [ ] `PYTHONPATH=. python -m pytest tests/ -q` passes
- [ ] `cd web && pnpm run build:prod && pnpm run verify-build` passes
- [ ] Safety gates pass on candidate (`scraper/safety_gates.py` / refresh pipeline)
- [ ] `automation_ran_at`, `run_id`, and import timestamps present on all auctions
- [ ] No unexpected source-count drop (>40% without `allow_large_drop`)
- [ ] Display enrichment regression auctions spot-checked: 582972, 584985, 588051

## Build verification

- [ ] `web/out/data/auctions.json` count ≥ 1000
- [ ] `web/out/data/export-meta.json` present with fresh `automation_ran_at`
- [ ] `web/out/status/index.html` loads import dashboard
- [ ] `web/out/robots.txt` and canonical meta in `index.html`
- [ ] No absolute `/pdfs/`, `/docs/`, `/thumbs/` paths in export JSON
- [ ] `.htaccess` disables cache for `auctions-data.js` and `export-meta.json`

## Deploy

- [ ] `scraper/deploy.py` / `refresh_and_deploy --deploy` completed without errors
- [ ] `scraper/http_verify.py` green against live `SITE_BASE_URL`
- [ ] `scraper/freshness_check.py` warn-only or strict check passes post-deploy
- [ ] Live site shows updated **Automation ran** timestamp in header
- [ ] Search `582972` returns expected card with **Imported** line

## Post-deploy ops

- [ ] UptimeRobot monitors configured (see `docs/MONITORING.md`)
- [ ] `NOTIFY_WEBHOOK_URL` secret set for CI failure alerts
- [ ] `NEXT_PUBLIC_GA_MEASUREMENT_ID` set in build secrets if analytics desired
- [ ] Document any known source limitations on `/auctions/status/`

## Rollback

- [ ] Previous `auctions.json` artifact retained in `work/runs/` or git tag
- [ ] Rollback = redeploy prior `web/out` artifact via `scraper/deploy.py`
