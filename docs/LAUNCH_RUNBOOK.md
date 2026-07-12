# Launch Runbook

Operations guide for staged launch of Scrap Auction India (Anvil Phase 006).

## Scope

This runbook covers **launch readiness**, not public marketing. The site is already public. Launch means inviting serious buyers, collecting feedback, and eventually enabling paid conversion — only after gates pass.

**Out of scope for this phase:**

- Deploy (unless explicitly requested)
- Full scrape runs
- Live billing / payment SDKs
- Automated outreach
- Mobile app (Phase 7)

## Launch stages

| Stage | Purpose | Billing |
|-------|---------|---------|
| `internal` | Gate automation, team QA | Disabled |
| `soft_launch` | Known buyers, feedback loop | Disabled |
| `paid_beta` | Manual invites, pricing validation | After legal/provider/buyer gates |
| `public_launch` | Broader channels after product proof | Live when approved |

**Launch approval is always manual.** The readiness report never sets `launch_approved: true`.

## Running launch gates

### Local / CI

```bash
cd web
pnpm run build:prod
pnpm run verify-build
```

The verify chain includes:

1. `node scripts/generate-launch-readiness.mjs` — writes JSON + markdown
2. `node scripts/verify-launch-readiness.mjs` — structural and policy checks

### Artifacts

| File | Purpose |
|------|---------|
| `web/out/launch-readiness.json` | Machine-readable gate report |
| `web/out/launch-readiness.md` | Human-readable summary |
| `web/out/data/launch-readiness.json` | Loaded by `/launch-readiness/` page |
| `web/public/data/launch-readiness.json` | Dev / next static copy |

### Internal dashboard

- **URL:** `https://scrapauctionindia.com/auctions/launch-readiness/`
- **Index policy:** `noindex` — excluded from `sitemap.xml`
- **Navigation:** Linked from `/status/` operations section only — not in the public Legal footer

Review these artifacts before soft launch:

| File | Purpose |
|------|---------|
| `web/out/launch-readiness.json` | Machine-readable gate report (CI artifact) |
| `web/out/launch-readiness.md` | Human-readable summary for owner review |

## Gate groups

1. **Data & sources** — count ≥ 1000, three sources, no capped MSTC-only export, timestamps, freshness
2. **Scraper & automation** — production workflow, safety gates, HTTP/freshness scripts
3. **SEO** — sitemap, canonicals, robots, seo-report, no staging leaks
4. **Analytics** — funnel events, env-gated GA
5. **Paywall & revenue** — pricing/plans/entitlements, checkout disabled, no payment SDK
6. **Legal, trust & support** — disclaimer, terms/privacy/refund, support, feedback path
7. **UX & detail pages** — sample detail export, design verifiers, no public export
8. **Launch ops & docs** — runbooks, manual approval gates

## Hard blockers vs warnings

- **Hard blockers** (`fail`/`blocked` + `blocker: true`) — must resolve before soft launch
- **Warnings** — informational; readiness score includes them but does not auto-block
- **Manual gates** — legal review, provider decision, buyer validation, launch approval. These block **paid beta** and **public launch** only; soft launch may proceed when hard blockers are clear.

## Pre-soft-launch checklist

- [ ] `pnpm run build:prod && pnpm run verify-build` passes
- [ ] `launch-readiness.json` shows zero hard blockers (or documented exceptions)
- [ ] `/status/` shows fresh `automation_ran_at` and three-source counts
- [ ] `docs/SOFT_LAUNCH_PLAYBOOK.md` reviewed
- [ ] `docs/BUYER_FEEDBACK_SOP.md` ready
- [ ] Outreach templates reviewed (`docs/LAUNCH_OUTREACH_TEMPLATES.md`) — **do not send automatically**

## Pre-paid-beta checklist

All soft-launch items, plus:

- [ ] Legal counsel reviewed terms, privacy, refund (`docs/PAYWALL_RUNBOOK.md`)
- [ ] Payment provider chosen and documented
- [ ] Buyer validation from soft launch documented
- [ ] Owner explicit approval to enable checkout env flags
- [ ] Checkout still returns stub until provider integration is complete

## Monitoring

See `docs/MONITORING.md` for freshness, HTTP verify, and uptime. On alert:

1. Open `/status/` and `/launch-readiness/`
2. Run `PYTHONPATH=. python -m scraper.status_report --check-live`
3. Do not deploy broken exports

## Rollback

See `docs/RELEASE_CHECKLIST.md` and `docs/PRODUCTION_STATUS.md`. Rollback = redeploy last good `web/out` artifact.

## Related docs

- `docs/SOFT_LAUNCH_PLAYBOOK.md`
- `docs/BUYER_FEEDBACK_SOP.md`
- `docs/LAUNCH_OUTREACH_TEMPLATES.md`
- `docs/LAUNCH_REPORT_TEMPLATE.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/PAYWALL_RUNBOOK.md`
- `docs/SEO_ANALYTICS_RUNBOOK.md`
