# Paywall Runbook

Operations guide for Scrap Auction India monetization foundation (Anvil Phase 005).

## Scope

This phase delivers a **provider-neutral paywall shell**:

- Plan and entitlement model
- Pricing, account, legal, and support pages
- Soft gates on premium workflows
- Paywall analytics events
- Disabled checkout stub (no live billing)

Live auth, payment provider SDKs, and subscription state are **deferred** until secrets, legal review, and buyer validation.

## Feature map

| Workflow | Free | Pro | Trader | Team | Enterprise |
|---|---|---|---|---|---|
| Search & basic filters | ✓ | ✓ | ✓ | ✓ | ✓ |
| Official source/PDF links | ✓ | ✓ | ✓ | ✓ | ✓ |
| Watchlist | 5 | 25 | 100 | 250 | Custom |
| Saved searches | 2 | 10 | 50 | 100 | Custom |
| Premium filters (radius, EMD fit, GST, material tree, large lots) | — | ✓ | ✓ | ✓ | ✓ |
| Advanced diligence / landed-cost assumptions | Preview | Preview | ✓ | ✓ | ✓ |
| WhatsApp closing reminders | — | — | ✓ | ✓ | ✓ |
| AI deep summaries | — | — | — | ✓ | ✓ |
| Team collaboration | — | — | — | Planned | ✓ |
| Controlled export | — | — | — | — | ✓ |

Source of truth in code:

- `web/src/lib/plans.ts`
- `web/src/lib/entitlements.ts`

## SEO-safe paywall policy

**Always public (indexable where appropriate):**

- Discover home and SEO landing pages
- Auction detail pages (`/[source]/[id]/`)
- Official source URLs and PDF/document links on cards and detail pages
- `/pricing/` (business-facing, indexable)

**Utility pages (noindex):**

- `/account/`, `/support/`, `/terms/`, `/privacy/`, `/refund-policy/`
- Existing utility surfaces: `/map/`, `/watchlist/`, `/saved/`, `/insights/`, `/status/`

**Footer navigation policy:**

- Footer links may point to noindex utility pages (watchlist, map, terms, support, account) for buyer navigation.
- Those pages must **never** appear in `sitemap.xml` or be treated as SEO landing targets.
- Only indexable business/commerce page in paywall scope: `/pricing/`.

**Never reintroduce:**

- Public bulk CSV/export controls

## Analytics funnel

Events (GA4, low-cardinality params only):

| Event | When |
|---|---|
| `pricing_page_view` | Pricing page mount |
| `plan_select` | User selects a plan card CTA |
| `upgrade_prompt_view` | Upgrade modal shown |
| `upgrade_cta_click` | Upgrade modal CTA (pricing, waitlist, enterprise) |
| `gated_feature_attempt` | User hits a soft gate |
| `checkout_start_stub` | Checkout handoff attempted (disabled) |
| `enterprise_inquiry_click` | Enterprise/support contact CTA |
| `account_page_view` | Account page mount |

Verification: `node web/scripts/verify-analytics.mjs` and `node web/scripts/verify-paywall.mjs`.

Suggested funnel review in GA4:

1. `gated_feature_attempt` → `upgrade_prompt_view`
2. `upgrade_prompt_view` → `upgrade_cta_click`
3. `upgrade_cta_click` → `pricing_page_view` / `plan_select`
4. Post-launch: `checkout_start_stub` → purchase success (future)

See also: `docs/SEO_ANALYTICS_RUNBOOK.md`.

`seo-report.json` includes a `paywall_funnel` section after build verification (conversion events wired; checkout remains disabled).

## Pre-live gates (required before enabling billing)

### Legal review gate

- `/terms/`, `/privacy/`, and `/refund-policy/` are **draft** copies for engineering only.
- Do not enable live checkout or collect payments until counsel reviews all three pages and pricing copy.
- Remove “billing not live” disclaimers only after legal sign-off.

### Payment provider decision gate

Evaluate providers against Indian B2B subscription needs (UPI, cards, netbanking, GST invoices, webhooks):

| Provider | Notes |
|---|---|
| **Razorpay** | Strong UPI/cards in India; subscriptions + invoices; common for SaaS |
| **Stripe** | Excellent DX; India entity/support varies — confirm subscription + GST invoice fit |
| **Cashfree** | India-focused; subscriptions and payment links |
| **Instamojo** | Simpler for smaller merchants; confirm recurring/subscription APIs |

Decision criteria:

- Recurring subscription support (not one-time only)
- GST tax invoice generation for B2B buyers
- Webhook reliability for `active` / `past_due` / `cancelled`
- No secrets in static export (`NEXT_PUBLIC_*` flags only)
- Refund/chargeback workflow documented

Document the chosen provider and webhook mapping in this runbook before implementation.

### Buyer validation gate

Before enabling checkout in production:

- [ ] Show pricing and upgrade flows to 5–10 real buyers (yards, brokers, trading desks)
- [ ] Confirm willingness to pay at hypothesis price points (Pro ₹2,999, Trader ₹4,999, etc.)
- [ ] Capture objections on gating (watchlist cap, filters, diligence)
- [ ] Explicit owner approval to proceed with live billing sub-round

Early-access waitlist today: email **support@scrapauctionindia.com** from `/account/?waitlist=1` or `/support/`.

## Local demo plan simulation

For UI verification only (not real billing):

```bash
# .env.local or build env
NEXT_PUBLIC_PAYWALL_DEMO_MODE=true
```

Then open `/account/` and select a simulated plan. Storage key: `mstc_paywall_demo_plan_v1` (localStorage).

## Future live billing activation

### 1. Provider choice (neutral requirements)

- Indian payments: cards, UPI, netbanking where possible
- GST invoice support for B2B buyers
- Webhook-based subscription status
- No secrets in the static export or git

Placeholders in `.env.example`:

- `NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED`
- `NEXT_PUBLIC_BILLING_PROVIDER`
- `BILLING_WEBHOOK_SECRET` (server/CI only — never `NEXT_PUBLIC_`)

### 2. Auth

- Accounts required before cross-device entitlements
- Sign-in placeholder today at `/account/`
- Map watchlist/saved searches from localStorage to user records on migration

### 3. Legal checklist before launch

- [ ] Counsel review of `/terms/`, `/privacy/`, `/refund-policy/`
- [ ] Pricing copy approved (hypothesis → live)
- [ ] Payment-not-live disclaimer removed only when checkout is real
- [ ] Enterprise order form and SLA
- [ ] Data processing agreement if using third-party billing

### 4. Enable checkout (later sub-round)

1. Set `NEXT_PUBLIC_BILLING_PROVIDER` and server webhook secret in CI only
2. Implement provider handoff in `web/src/lib/checkout.ts`
3. Replace waitlist CTAs with live checkout on pricing/upgrade surfaces
4. Remove or gate demo plan override in production builds
5. Run full `pnpm run verify-build` and paywall tests

### 5. Post-launch ops

- Monitor funnel events weekly
- Track churn and gated-feature attempts by `feature` param
- Keep official source links ungated permanently

## Verification commands

```bash
cd web && pnpm run build:prod
cd web && pnpm run verify-build
node web/scripts/verify-paywall.mjs
PYTHONPATH=. python3 -m pytest tests/test_paywall.py -q
```

## Revenue planning anchor

Internal target: **₹3,00,000/month** recurring (see `docs/product-planning/rounds/FORGE_009_PAYWALL_STRATEGY.md`).

Hypothesis pricing (not yet charged):

| Plan | ₹/month | Users for ~₹3L |
|---|---:|---:|
| Pro | 2,999 | 100 |
| Trader | 4,999 | 60 |
| Team | 9,999 | 30 |
| Enterprise | 24,999 | 12 |
