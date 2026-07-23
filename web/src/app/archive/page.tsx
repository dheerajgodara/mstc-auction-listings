import type { Metadata } from "next";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ArchiveClientFilters } from "@/components/archive-client-filters";
import { SiteDisclaimer } from "@/components/site-disclaimer";
import { SiteFooter } from "@/components/site-footer";
import { loadArchiveAuctionsAtBuild } from "@/lib/load-auction-at-build";
import { landingPageQualifies } from "@/lib/seo/index-policy";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
import { absoluteUrl, SITE_BASE_URL } from "@/lib/site-url";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";

const PATH = "/archive/";

export function generateMetadata(): Metadata {
  const data = loadArchiveAuctionsAtBuild();
  const count = data.auctions?.length ?? 0;
  const indexable = landingPageQualifies(count, 10);
  return {
    title: "Auction Archive | Scrap Auction India",
    description:
      "Short-window and recently closed MSTC/GeM auctions kept for 30 days — searchable research archive for buyers and AI agents.",
    alternates: { canonical: absoluteUrl(PATH) },
    robots: indexable ? { index: true, follow: true } : NOINDEX_METADATA.robots,
  };
}

export default function ArchivePage() {
  const data = loadArchiveAuctionsAtBuild();
  const auctions = (data.auctions ?? []).map((a) => enrichAuctionDisplay(a));

  return (
    <AppShell>
      <main className="container-marketplace space-y-8 py-10">
        <header className="max-w-3xl space-y-3">
          <Link href={SITE_BASE_URL} className="text-body-sm link-action">
            Browse live auctions
          </Link>
          <h1 className="text-display text-foreground">Auction Archive</h1>
          <p className="text-body text-muted-foreground">
            Same-day and short-window listings that miss the live 12-hour runway, plus recently
            closed auctions — retained for about 30 days after closing.
          </p>
          <p className="text-body-sm text-muted-foreground">
            Catalogues appear when captured. Always verify quantity, EMD, and closing on the
            official portal before bidding.
          </p>
          <p className="text-body-sm font-medium text-foreground">
            {auctions.length} archive auction{auctions.length === 1 ? "" : "s"} in this build
            {data.generated_at ? ` · updated ${data.generated_at}` : ""}.
          </p>
        </header>

        {/* Crawlable SSR snapshot for agents (first 80). */}
        <noscript>
          <ol className="space-y-3" data-crawlable-archive-list="true">
            {auctions.slice(0, 80).map((a) => (
              <li key={a.id}>
                {(a.display_title || a.auction_number || a.id) +
                  (a.closing ? ` · closes ${a.closing}` : "")}
              </li>
            ))}
          </ol>
        </noscript>

        <ArchiveClientFilters initial={auctions} />
        <SiteDisclaimer />
      </main>
      <SiteFooter automationRanAt={data.generated_at} />
    </AppShell>
  );
}
