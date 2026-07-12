# Soft Launch Playbook

Controlled soft launch for Scrap Auction India — invite known buyers before paid conversion or broad marketing.

## Goals

1. Validate discovery UX with real buyers (search, filters, detail, official links).
2. Collect structured feedback without support overload.
3. Prove data freshness and three-source coverage under real use.
4. Identify UX blockers before paywall or public launch.

## Non-goals

- Mass email or automated outreach (templates are docs only)
- Live billing
- SEO/content marketing push
- Claiming government affiliation

## Prerequisites

- `pnpm run verify-build` passes
- `/launch-readiness/` shows recommended stage at least `soft_launch` (no hard blockers)
- `/status/` shows multi-source counts and recent automation timestamp
- `docs/BUYER_FEEDBACK_SOP.md` owner assigned

## Audience (initial cohort)

Target 10–30 known buyers:

- Scrap traders and metal processors
- Industrial surplus buyers
- Vehicle auction participants
- Existing network contacts (not cold lists)

## Invitation flow

1. **Select cohort** — spreadsheet: name, company, material interest, WhatsApp/email.
2. **Personal invite** — use templates in `docs/LAUNCH_OUTREACH_TEMPLATES.md` (manual send only).
3. **Set expectations:**
   - Free access to search, detail, official source/PDF links
   - Billing not live; pricing page is informational
   - Feedback requested via support form or direct channel
4. **Share links:**
   - Discover: `https://scrapauctionindia.com/auctions/`
   - Status: `https://scrapauctionindia.com/auctions/status/`
   - Support: `https://scrapauctionindia.com/auctions/support/`

## Session guide (send to invitees)

Ask buyers to try:

1. Search for a material or auction ID (e.g. `582972`)
2. Apply filters (source, state, closing soon)
3. Open a detail page and follow an official source link
4. Save one auction to watchlist (local, no account required)
5. Report anything confusing via Support

## Duration

- **Minimum:** 2 weeks
- **Extend if:** freshness incidents, critical UX bugs, or &lt;5 substantive feedback items

## Success signals

| Signal | Target |
|--------|--------|
| Invitees who complete search → detail → source click | ≥ 60% |
| Critical bugs filed | 0 unresolved at end |
| Data freshness complaints | 0 |
| Buyers who say they'd return weekly | ≥ 40% of respondents |

## Exit criteria (ready for paid beta consideration)

- [ ] Hard blockers cleared on `/launch-readiness/`
- [ ] Top 3 UX issues from feedback addressed or documented
- [ ] Legal pages reviewed (manual gate)
- [ ] Provider decision documented (manual gate)
- [ ] Owner approval for paid beta cohort

## What not to do

- Do not enable `NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED`
- Do not add payment SDKs
- Do not run full scrape outside scheduled automation
- Do not deploy without release checklist

## Incident response

If production data drops or goes stale during soft launch:

1. Pause new invites
2. Check `/status/` and monitoring alerts
3. Follow `docs/PRODUCTION_STATUS.md` recovery steps
4. Notify cohort if listings were affected

## Post-soft-launch

Fill `docs/LAUNCH_REPORT_TEMPLATE.md` and store in `work/launch-reports/` (gitignored if containing PII).
