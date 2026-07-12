# Release Checklist

Use this checklist before promoting a candidate export to production (Hostinger).

## Pre-merge

- [ ] `web/public/data/auctions.json` exists, is not zero bytes, and count ≥ 1000 (build fails early via `finalize_public_export` / `generate-auction-routes` if empty)
- [ ] `PYTHONPATH=. python -m pytest tests/ -q` passes
- [ ] `cd web && pnpm run build:prod && pnpm run verify-build` passes
- [ ] Safety gates pass on candidate (`scraper/safety_gates.py` / refresh pipeline)
- [ ] `automation_ran_at`, `run_id`, and import timestamps present on all auctions
- [ ] No unexpected source-count drop (>40% without `allow_large_drop`)
- [ ] Display enrichment regression auctions spot-checked: 582972, 584985, 588051

## Build verification

- [ ] `web/out/data/auctions.json` count ≥ 1000
- [ ] `web/out/data/auction-routes.json` present with `route_id` per auction
- [ ] `web/out/sitemap.xml` uses `https://scrapauctionindia.com/auctions/` (no query URLs)
- [ ] `web/out/sitemap.xml` includes `/pricing/` and excludes noindex paywall utility URLs
- [ ] Sample detail pages exist: `web/out/mstc/582972/index.html` (and 584985, 588051)
- [ ] `web/out/data/export-meta.json` present with fresh `automation_ran_at`
- [ ] `web/out/status/index.html` loads import dashboard (noindex)
- [ ] `web/out/robots.txt` references sitemap; canonical meta uses `scrapauctionindia.com`
- [ ] `web/out/seo-report.json` and `web/out/sitemap-summary.json` generated (`pnpm run verify-build` tail)
- [ ] `web/out/launch-readiness.json` and `web/out/launch-readiness.md` reviewed before soft launch (`node web/scripts/verify-launch-readiness.mjs`)
- [ ] SEO/analytics runbook reviewed: `docs/SEO_ANALYTICS_RUNBOOK.md`
- [ ] Utility pages (`map`, `watchlist`, `saved`, `insights`, `liquidate`) emit `noindex`
- [ ] Paywall utility pages (`account`, `support`, `terms`, `privacy`, `refund-policy`) emit `noindex`; `/pricing/` indexable and in sitemap
- [ ] **Browser review:** manually open `/pricing/`, `/account/?waitlist=1`, `/support/`, `/terms/`, `/privacy/`, `/refund-policy/` — confirm copy, waitlist CTAs, and no live billing UI
- [ ] **Legal review gate:** counsel has reviewed terms/privacy/refund before any live billing (pages are draft until then)
- [ ] **Provider decision gate:** payment provider chosen and documented in `docs/PAYWALL_RUNBOOK.md`
- [ ] **Buyer validation gate:** early-access feedback collected; owner approval before checkout enablement
- [ ] `node web/scripts/verify-paywall.mjs` passes after `verify-build`
- [ ] `docs/PAYWALL_RUNBOOK.md` reviewed; billing placeholders only in `.env.example`
- [ ] No live payment SDK or secrets in source; checkout stub stays disabled
- [ ] Airbnb marketplace design: tokens/chrome/cards; `pnpm run verify-deploy-prereqs` and `verify-airbnb-design.mjs` pass
- [ ] No absolute `/pdfs/`, `/docs/`, `/thumbs/` paths in export JSON
- [ ] No public CSV/export controls in UI (`verify-build` scans `web/src`)
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
- [ ] Google Search Console: upload verification file to `web/public/` if needed, then submit `https://scrapauctionindia.com/auctions/sitemap.xml`
- [ ] Document any known source limitations on `/auctions/status/`

## Rollback

- [ ] Previous `auctions.json` artifact retained in `work/runs/` or git tag
- [ ] Rollback = redeploy prior `web/out` artifact via `scraper/deploy.py`
