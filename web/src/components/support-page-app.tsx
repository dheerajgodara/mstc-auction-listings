"use client";

import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { trackEnterpriseInquiryClick } from "@/lib/analytics";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

export function SupportPageApp() {
  return (
    <AppShell>
      <main className="container-marketplace space-y-6 py-section">
        <h1 className="text-display text-foreground">Support</h1>
        <section className="surface-elevated space-y-3 p-6">
          <h2 className="text-headline text-foreground">Buyer support</h2>
          <p className="text-body-sm text-muted-foreground">
            For data issues on a listing, use the report form in the diligence
            panel on any auction card. For billing, access, or Enterprise inquiries
            before launch:
          </p>
          <p className="text-body">
            <a
              href="mailto:support@scrapauctionindia.com"
              className="link-action"
              onClick={() => trackEnterpriseInquiryClick({ source: "support" })}
            >
              support@scrapauctionindia.com
            </a>
          </p>
          <p className="text-footnote text-muted-foreground">
            Response times for paid tiers will be published when billing goes live.
          </p>
        </section>
        <section className="surface-elevated space-y-3 p-6">
          <h2 className="text-headline text-foreground">Early access waitlist</h2>
          <p className="text-body-sm text-muted-foreground">
            Paid plans are in early access. Billing is not live — join the
            waitlist by email and we will confirm next steps when checkout opens.
          </p>
          <p className="text-body">
            <a
              href="mailto:support@scrapauctionindia.com?subject=Early%20access%20waitlist"
              className="link-action"
              onClick={() => trackEnterpriseInquiryClick({ source: "support_waitlist" })}
            >
              support@scrapauctionindia.com
            </a>
          </p>
          <Link
            href={resolveAppPath("account/?waitlist=1")}
            className="btn-secondary inline-flex text-sm"
          >
            Waitlist instructions
          </Link>
        </section>
        <section className="surface-elevated space-y-3 p-6">
          <h2 className="text-headline text-foreground">Enterprise sales</h2>
          <p className="text-body-sm text-muted-foreground">
            Custom reporting, controlled export, and onboarding for yards and
            trading desks.
          </p>
          <Link
            href={resolveAppPath("pricing/")}
            className="btn-primary inline-flex text-sm"
            onClick={() => trackEnterpriseInquiryClick({ source: "support_enterprise" })}
          >
            View Enterprise plan
          </Link>
        </section>
        <SiteFooter />
      </main>
    </AppShell>
  );
}
