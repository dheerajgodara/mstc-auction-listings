# Buyer Feedback SOP

Standard process for collecting and acting on buyer feedback during soft launch and paid beta.

## Channels

| Channel | Use | Owner action SLA |
|---------|-----|------------------|
| `/support/` report form | Bugs, confusion, feature requests | 2 business days |
| Direct WhatsApp / email | Soft-launch cohort | Same day for blockers |
| Analytics (GA4) | Funnel drops, no-results spikes | Weekly review |
| `/status/` | Data freshness disputes | Same day |

## Triage categories

1. **P0 — Blocker** — Wrong/missing auctions, broken official links, site down, misleading copy
2. **P1 — Major UX** — Cannot find listings, filter broken, mobile unusable
3. **P2 — Enhancement** — Feature request, copy tweak, nice-to-have
4. **P3 — Noise** — Out of scope, duplicate, spam

## Intake template

Record each item:

```text
ID: FB-YYYYMMDD-###
Date:
Reporter:
Cohort: soft_launch | paid_beta | public
Category: P0 | P1 | P2 | P3
Summary:
Steps to reproduce:
Auction ID / URL (if any):
Expected:
Actual:
Screenshot: yes/no
Resolution:
Status: open | fixed | wont_fix | deferred
```

## Response templates

**Acknowledgment (within 24h):**

> Thanks for the report. We've logged this as [ID] and will follow up by [date]. Official bidding always happens on the source portal linked from each listing.

**Fixed:**

> We resolved [ID]: [one-line fix]. Please refresh and try again. If anything still looks off, reply with the auction ID.

**Won't fix (with reason):**

> Thanks for [ID]. We're not pursuing this now because [reason]. We've noted it for a future phase.

## Weekly review cadence

1. Export open P0/P1 count
2. Check `no_results` and `search` analytics trends
3. Cross-check `/launch-readiness/` warnings
4. Update `docs/LAUNCH_REPORT_TEMPLATE.md` summary section

## Paid launch gate

Do not enable live billing until:

- [ ] Zero open P0 items
- [ ] P1 items have owner-approved deferrals
- [ ] At least 5 soft-launch buyers confirm value (qualitative)
- [ ] Legal and provider manual gates complete (`docs/PAYWALL_RUNBOOK.md`)

## Privacy

- Do not commit buyer PII to the repo
- Store detailed feedback in private notes or `work/launch-reports/` (gitignored)
- Redact names in public launch reports

## Escalation

| Condition | Action |
|-----------|--------|
| Data wrong vs official source | P0 — verify scraper, do not deploy bad export |
| Official link blocked | P0 — revert any change that blocks outbound links |
| Payment question before billing live | Redirect to pricing FAQ; no manual charges |
