# Launch Report Template

Copy this file to `work/launch-reports/YYYY-MM-DD-launch-report.md` after each soft-launch or milestone review. Redact PII before sharing.

## Metadata

| Field | Value |
|-------|-------|
| Report date | |
| Phase | soft_launch / paid_beta / public_launch |
| Author | |
| Launch approved | No (manual only) |
| Readiness score | % (from `/launch-readiness/` or `launch-readiness.json`) |
| Recommended stage | |

## Executive summary

2–3 sentences: cohort size, overall health, go/no-go for next stage.

## Data health

| Metric | Value |
|--------|-------|
| Total auctions | |
| MSTC | |
| GeM Forward | |
| eAuction | |
| automation_ran_at | |
| Freshness within 36h | yes/no |
| Hard blockers (launch gates) | |

## Gate summary

| Group | Pass | Warn | Fail | Manual |
|-------|------|------|------|--------|
| Data & sources | | | | |
| Scraper & automation | | | | |
| SEO | | | | |
| Analytics | | | | |
| Paywall & revenue | | | | |
| Legal & support | | | | |
| UX | | | | |
| Launch ops | | | | |

## Funnel metrics (GA4)

| Event | Period count | Notes |
|-------|--------------|-------|
| page_view | | |
| search | | |
| view_auction_detail | | |
| source_open | | |
| pdf_open | | |
| watchlist_toggle | | |
| pricing_page_view | | |
| launch_readiness_page_view | | |

## Cohort feedback

| ID | Priority | Summary | Status |
|----|----------|---------|--------|
| FB- | P0/P1/P2 | | open/fixed |

## UX blockers resolved

-

## UX blockers open

-

## Paid launch gates (manual)

| Gate | Status | Notes |
|------|--------|-------|
| Legal review | pending / done | |
| Provider decision | pending / done | |
| Buyer validation | pending / done | |
| Owner launch approval | pending / done | |
| Live billing enabled | no | must stay no until approved |

## Decision

- [ ] Continue soft launch
- [ ] Proceed to paid beta (manual approval)
- [ ] Hold — blockers listed above
- [ ] Public launch (manual approval only)

## Next actions

1.
2.
3.

## Attachments

- `launch-readiness.json` snapshot path:
- `launch-readiness.md` snapshot path:
- `seo-report.json` snapshot path:
