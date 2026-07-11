import type { Metadata } from "next";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Liquidate scrap & surplus assets",
  description:
    "Enterprise intake for government and PSU asset disposal listings.",
  ...NOINDEX_METADATA,
};

export default function LiquidatePage() {
  return (
    <AppShell>
      <main className="container-marketplace space-y-6 py-section">
        <Link href={resolveAppPath("")} className="text-body-sm link-action">
          Browse auctions
        </Link>
        <h1 className="text-display">Liquidate scrap / sell with us</h1>
        <p className="text-body text-muted-foreground">
          Plant managers and enterprises can list surplus scrap, machinery, and
          vehicles for discovery by verified buyers. This portal aggregates
          public auctions — contact us to discuss listing support or disposal
          partnerships.
        </p>
        <a
          href="mailto:contact@scrapauctionindia.com?subject=Enterprise%20liquidation%20inquiry"
          className="btn-primary inline-flex"
        >
          Contact enterprise team
        </a>
        <p className="text-footnote text-muted-foreground">
          Bidding and payments always occur on official government portals
          (MSTC, GeM, eAuction).
        </p>
      </main>
      <SiteFooter />
    </AppShell>
  );
}
