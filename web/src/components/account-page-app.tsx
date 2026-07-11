"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { AccountStatus } from "@/components/account-status";
import { trackAccountPageView } from "@/lib/analytics";
import {
  getCurrentPlan,
  isDemoPlanModeEnabled,
  loadDemoPlanOverride,
  saveDemoPlanOverride,
} from "@/lib/entitlements";
import { PLAN_CATALOG, PLAN_IDS, type PlanId } from "@/lib/plans";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

export function AccountPageApp() {
  const [plan, setPlan] = useState<PlanId>("free");
  const demoMode = isDemoPlanModeEnabled();
  const searchParams = useSearchParams();
  const waitlistIntent = searchParams.get("waitlist") === "1";

  useEffect(() => {
    trackAccountPageView();
    setPlan(getCurrentPlan());
  }, []);

  return (
    <AppShell>
      <main className="container-marketplace space-y-6 py-section">
        <header>
          <h1 className="text-display text-foreground">Account</h1>
          <p className="mt-2 text-body-sm text-muted-foreground">
            Sign-in and subscriptions are not live yet. This page shows your
            local plan status and how to join early access.
          </p>
        </header>

        {waitlistIntent ? (
          <section
            className="surface-elevated space-y-3 border border-action/30 bg-action/5 p-6"
            aria-labelledby="waitlist-heading"
          >
            <h2 id="waitlist-heading" className="text-headline text-foreground">
              Early access waitlist
            </h2>
            <p className="text-body-sm text-muted-foreground">
              Billing is not live. To request early access when checkout opens,
              email us with your preferred plan and buyer use case (yard, broker,
              or trading desk).
            </p>
            <p className="text-body">
              <a
                href="mailto:support@scrapauctionindia.com?subject=Early%20access%20waitlist"
                className="btn-primary inline-flex text-sm"
              >
                Email support@scrapauctionindia.com
              </a>
            </p>
            <p className="text-footnote text-muted-foreground">
              Or visit{" "}
              <Link href={resolveAppPath("support/")} className="link-action">
                Support
              </Link>{" "}
              for Enterprise inquiries. We will confirm next steps when auth and
              billing are enabled — no payment is collected on this site today.
            </p>
          </section>
        ) : null}

        <AccountStatus plan={plan} />

        <section className="surface-elevated space-y-4 p-6">
          <h2 className="text-headline text-foreground">Sign-in (coming soon)</h2>
          <p className="text-body-sm text-muted-foreground">
            Accounts will connect watchlists, saved searches, and billing across
            devices. Passwords and payment data are not collected on this static
            site today.
          </p>
          <button type="button" className="btn-secondary" disabled>
            Sign in — not available
          </button>
        </section>

        {demoMode ? (
          <section
            className="surface-elevated space-y-4 border-2 border-action/50 bg-muted p-6"
            role="note"
            aria-labelledby="demo-plan-heading"
          >
            <p className="text-footnote font-semibold uppercase tracking-wide text-foreground">
              Demo mode active — not real billing
            </p>
            <h2 id="demo-plan-heading" className="text-headline text-foreground">
              Local demo plan (verification only)
            </h2>
            <p className="text-body-sm text-muted-foreground">
              This override is for UI testing on this device only. It does not
              prove entitlements, create a subscription, or sync across browsers.
            </p>
            <label className="block text-body-sm">
              Simulate plan
              <select
                className="mt-1 h-10 w-full max-w-xs rounded-lg border border-border bg-card px-3"
                value={loadDemoPlanOverride() ?? "free"}
                onChange={(e) => {
                  const v = e.target.value as PlanId;
                  saveDemoPlanOverride(v === "free" ? null : v);
                  setPlan(getCurrentPlan());
                }}
              >
                {PLAN_IDS.map((id) => (
                  <option key={id} value={id}>
                    {PLAN_CATALOG[id].name}
                  </option>
                ))}
              </select>
            </label>
          </section>
        ) : (
          <p className="text-footnote text-muted-foreground">
            Demo plan simulation is disabled. Set{" "}
            <code className="rounded bg-muted px-1">NEXT_PUBLIC_PAYWALL_DEMO_MODE=true</code>{" "}
            in a local build to test entitlements.
          </p>
        )}

        <p className="text-body-sm">
          <Link href={resolveAppPath("pricing/")} className="link-action">
            View pricing
          </Link>
          {" · "}
          <Link href={resolveAppPath("support/")} className="link-action">
            Contact support
          </Link>
        </p>

        <SiteFooter />
      </main>
    </AppShell>
  );
}
