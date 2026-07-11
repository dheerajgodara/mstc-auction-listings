"use client";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";

export function AccessibilityPageApp() {
  return (
    <AppShell>
      <main className="container-marketplace space-y-6 py-section">
        <h1 className="text-display">Accessibility statement</h1>
        <p className="text-body text-muted-foreground">
          We aim to make government auction discovery usable for buyers with
          diverse needs across the Scrap Auction India marketplace.
        </p>
        <section className="surface-elevated max-w-3xl space-y-4 p-6">
          <h2 className="text-headline">Conformance</h2>
          <p className="text-body">
            This site targets WCAG 2.1 Level AA where feasible for a static,
            client-rendered discovery experience. Keyboard navigation, skip
            links, Rausch focus indicators, and live regions for result counts
            are implemented on the discover surface.
          </p>
          <h2 className="text-headline">Features</h2>
          <ul className="list-disc space-y-1 pl-5 text-body">
            <li>Skip to main content link on all shell pages</li>
            <li>44px minimum touch targets on primary actions</li>
            <li>Semantic headings and landmark regions</li>
            <li>Tabular numerals for commercial figures</li>
            <li>Reduced-motion respected for animated modules</li>
            <li>Visible focus rings using marketplace Rausch halo</li>
          </ul>
          <h2 className="text-headline">Known limitations</h2>
          <ul className="list-disc space-y-1 pl-5 text-body">
            <li>
              Third-party PDFs and source portals are outside our control
            </li>
            <li>
              Map tiles and some document previews may have limited text
              alternatives
            </li>
          </ul>
          <h2 className="text-headline">Feedback</h2>
          <p className="text-body">
            Report accessibility barriers to{" "}
            <a
              className="link-action"
              href="mailto:support@scrapauctionindia.com?subject=Accessibility"
            >
              support@scrapauctionindia.com
            </a>
            .
          </p>
        </section>
      </main>
      <SiteFooter />
    </AppShell>
  );
}
