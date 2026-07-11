"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { SiteDisclaimer } from "@/components/site-disclaimer";
import {
  trackCheckoutStartStub,
  trackEnterpriseInquiryClick,
  trackPlanSelect,
  trackPricingPageView,
  trackUpgradeCtaClick,
} from "@/lib/analytics";
import { startCheckoutStub } from "@/lib/checkout";
import {
  ENTITLEMENT_LABELS,
  ENTITLEMENTS,
  PLAN_CATALOG,
  PLAN_IDS,
  REVENUE_TARGET_INR,
  type EntitlementKey,
  type PlanId,
} from "@/lib/plans";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

const FAQ = [
  {
    q: "Is billing live?",
    a: "Not yet. This pricing page describes early-access plans. Checkout stays disabled until a payment provider, legal review, and buyer validation are complete.",
  },
  {
    q: "What stays free?",
    a: "Search, filters, SEO detail pages, and every official MSTC, GeM, and eAuction source or PDF link remain free.",
  },
  {
    q: "Why gate workflows instead of facts?",
    a: "Buyers need to verify listings on official portals. We charge for time-saving tools — watchlists, saved searches, premium filters, and diligence — not for access to public auction data.",
  },
  {
    q: "Can I export auction data?",
    a: "Public bulk export is not offered. Controlled export may be available on Enterprise after legal review.",
  },
];

const COMPARISON_ROWS: {
  label: string;
  entitlement?: EntitlementKey;
  free: string;
  pro: string;
  trader: string;
  team: string;
  enterprise: string;
}[] = [
  {
    label: "Watchlist capacity",
    free: "5 auctions",
    pro: "25",
    trader: "100",
    team: "250",
    enterprise: "Custom",
  },
  {
    label: "Saved searches",
    free: "2",
    pro: "10",
    trader: "50",
    team: "100",
    enterprise: "Custom",
  },
  {
    label: "Premium filters",
    entitlement: ENTITLEMENTS.PREMIUM_FILTERS,
    free: "—",
    pro: "✓",
    trader: "✓",
    team: "✓",
    enterprise: "✓",
  },
  {
    label: "Advanced diligence",
    entitlement: ENTITLEMENTS.ADVANCED_DILIGENCE,
    free: "Preview",
    pro: "Preview",
    trader: "✓",
    team: "✓",
    enterprise: "✓",
  },
  {
    label: "Closing alerts",
    entitlement: ENTITLEMENTS.ALERTS,
    free: "—",
    pro: "—",
    trader: "✓",
    team: "✓",
    enterprise: "✓",
  },
  {
    label: "AI deep summaries",
    entitlement: ENTITLEMENTS.AI_DEEP_SUMMARY,
    free: "—",
    pro: "—",
    trader: "—",
    team: "✓",
    enterprise: "✓",
  },
  {
    label: "Team seats",
    entitlement: ENTITLEMENTS.TEAM_COLLAB,
    free: "—",
    pro: "—",
    trader: "—",
    team: "Planned",
    enterprise: "✓",
  },
];

function formatRevenueTarget(): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(REVENUE_TARGET_INR);
}

export function PricingPageApp({ showHeader = true }: { showHeader?: boolean }) {
  const [selectedPlan, setSelectedPlan] = useState<PlanId | null>(null);

  useEffect(() => {
    trackPricingPageView();
    try {
      const highlightPlan = new URLSearchParams(window.location.search).get("plan");
      if (highlightPlan && PLAN_IDS.includes(highlightPlan as PlanId)) {
        setSelectedPlan(highlightPlan as PlanId);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const handlePlanCta = (planId: PlanId) => {
    trackPlanSelect(planId);
    if (planId === "enterprise") {
      trackEnterpriseInquiryClick({ source: "pricing" });
      window.location.href = resolvePublicUrl("support/");
      return;
    }
    if (planId === "free") {
      window.location.href = resolvePublicUrl("");
      return;
    }
    trackCheckoutStartStub({ plan: planId });
    const result = startCheckoutStub(planId);
    trackUpgradeCtaClick({
      plan: planId,
      feature: "pricing_card",
      cta: result.ok ? "checkout_stub" : "waitlist",
    });
    window.location.href = resolvePublicUrl("account/?waitlist=1");
  };

  return (
    <AppShell>
      <main className="container-marketplace space-y-10 py-section">
        {showHeader ? (
          <header className="mx-auto max-w-3xl text-center">
            <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
              Early access · hypothesis pricing
            </p>
            <h1 className="mt-2 text-display text-foreground">
              Plans for serious scrap buyers
            </h1>
            <p className="mt-3 text-body text-muted-foreground">
              Public discovery stays free. Upgrade when you need deeper filters,
              diligence, and alerts — without blocking official source verification.
            </p>
            <p className="mt-4 flex flex-wrap justify-center gap-x-3 gap-y-1 text-body-sm">
              <Link href={resolveAppPath("")} className="link-action">
                Discover auctions
              </Link>
              <Link href={resolveAppPath("mstc-auctions/")} className="link-action">
                MSTC auctions
              </Link>
              <Link href={resolveAppPath("mstc/582972/")} className="link-action">
                Sample listing
              </Link>
            </p>
            <p className="mt-2 text-footnote text-muted-foreground">
              Revenue design anchor: {formatRevenueTarget()}/month recurring (internal
              planning target).
            </p>
          </header>
        ) : (
          <p className="mx-auto max-w-3xl text-center text-footnote text-muted-foreground">
            Revenue design anchor: {formatRevenueTarget()}/month recurring (internal
            planning target).
          </p>
        )}

        <div className="grid gap-4 lg:grid-cols-3 xl:grid-cols-5">
          {PLAN_IDS.map((id) => {
            const plan = PLAN_CATALOG[id];
            const highlighted = selectedPlan === id;
            return (
              <article
                key={id}
                className={`surface-elevated flex flex-col p-5 ${
                  highlighted ? "ring-2 ring-action" : ""
                }`}
              >
                <h2 className="text-headline text-foreground">{plan.name}</h2>
                <p className="mt-1 text-body-sm text-muted-foreground">
                  {plan.tagline}
                </p>
                <p className="mt-4 text-display tabular-nums text-foreground">
                  {plan.priceLabel}
                </p>
                <p className="text-footnote text-muted-foreground">
                  {plan.billingNote}
                </p>
                <ul className="mt-4 flex-1 space-y-2 text-body-sm">
                  {plan.highlights.map((h) => (
                    <li key={h} className="flex gap-2">
                      <Check
                        className="mt-0.5 h-4 w-4 shrink-0 text-action"
                        aria-hidden
                      />
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  className={
                    id === "free" ? "btn-secondary mt-6 w-full" : "btn-primary mt-6 w-full"
                  }
                  onClick={() => handlePlanCta(id)}
                >
                  {id === "free"
                    ? "Continue free"
                    : id === "enterprise"
                      ? "Contact sales"
                      : "Join waitlist"}
                </button>
              </article>
            );
          })}
        </div>

        <section className="surface-elevated overflow-x-auto p-6">
          <h2 className="text-headline text-foreground">Feature comparison</h2>
          <table className="mt-4 w-full min-w-[640px] text-left text-body-sm">
            <thead>
              <tr className="border-b border-border text-footnote text-muted-foreground">
                <th className="py-2 pr-4">Feature</th>
                <th className="px-2 py-2">Free</th>
                <th className="px-2 py-2">Pro</th>
                <th className="px-2 py-2">Trader</th>
                <th className="px-2 py-2">Team</th>
                <th className="px-2 py-2">Enterprise</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON_ROWS.map((row) => (
                <tr key={row.label} className="border-b border-border/60">
                  <td className="py-3 pr-4 font-medium text-foreground">
                    {row.label}
                    {row.entitlement && (
                      <span className="mt-0.5 block text-footnote font-normal text-muted-foreground">
                        {ENTITLEMENT_LABELS[row.entitlement].description}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-3 tabular-nums">{row.free}</td>
                  <td className="px-2 py-3">{row.pro}</td>
                  <td className="px-2 py-3">{row.trader}</td>
                  <td className="px-2 py-3">{row.team}</td>
                  <td className="px-2 py-3">{row.enterprise}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="mx-auto max-w-3xl space-y-4">
          <h2 className="text-headline text-center text-foreground">FAQ</h2>
          {FAQ.map((item) => (
            <details
              key={item.q}
              className="surface-elevated group p-4"
            >
              <summary className="cursor-pointer text-title text-foreground">
                {item.q}
              </summary>
              <p className="mt-2 text-body-sm text-muted-foreground">{item.a}</p>
            </details>
          ))}
        </section>

        <section className="surface-elevated mx-auto max-w-3xl space-y-3 p-6">
          <h2 className="text-headline text-foreground">Source verification</h2>
          <SiteDisclaimer />
          <p className="text-body-sm text-muted-foreground">
            Paid plans do not replace official portals. Always confirm lot details,
            EMD, and terms on MSTC, GeM Forward, or eAuction.gov.in before bidding.
          </p>
          <p className="text-footnote text-muted-foreground">
            <Link href={resolveAppPath("terms/")} className="link-action">
              Terms
            </Link>
            {" · "}
            <Link href={resolveAppPath("privacy/")} className="link-action">
              Privacy
            </Link>
            {" · "}
            <Link href={resolveAppPath("refund-policy/")} className="link-action">
              Refund policy
            </Link>
            {" · "}
            <Link href={resolveAppPath("support/")} className="link-action">
              Support
            </Link>
          </p>
        </section>

        <SiteFooter />
      </main>
    </AppShell>
  );
}
