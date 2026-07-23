import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { absoluteUrl } from "@/lib/site-url";

const CANONICAL = absoluteUrl("developers/");
const DESCRIPTION =
  "Machine-readable auction feeds, API JSON, llms.txt, and sitemap contracts for Cursor agents and crawlers. Discovery only — bid on official portals.";

export const metadata: Metadata = {
  title: "Developers & agents | Scrap Auction India",
  description: DESCRIPTION,
  robots: { index: true, follow: true },
  alternates: { canonical: CANONICAL },
  openGraph: {
    title: "Developers & agents | Scrap Auction India",
    description: DESCRIPTION,
    url: CANONICAL,
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Developers & agents | Scrap Auction India",
    description: DESCRIPTION,
  },
};

const ENDPOINTS = [
  {
    path: "/auctions/api/manifest.json",
    note: "Counts, generated_at, endpoint list",
  },
  {
    path: "/auctions/api/schema.json",
    note: "Field descriptions for sanitized auction JSON",
  },
  {
    path: "/auctions/api/search-index.json",
    note: "Full slim index — filter locally (no ?q= API)",
  },
  {
    path: "/auctions/api/search/aluminium.json",
    note: "Prebuilt aluminium topic feed",
  },
  {
    path: "/auctions/api/search/closing-soon.json",
    note: "Prebuilt closing-soon topic feed",
  },
  {
    path: "/auctions/api/latest.json",
    note: "Newest indexable auctions (capped)",
  },
  {
    path: "/auctions/api/archive/latest.json",
    note: "T-30 archive — short-window + recently closed",
  },
  {
    path: "/auctions/api/archive/search-index.json",
    note: "Archive slim index — filter locally",
  },
  {
    path: "/auctions/api/auction/{source}/{id}.json",
    note: "One sanitized auction (may be listing_only until deep scrape)",
  },
  {
    path: "/auctions/archive/",
    note: "HTML archive — same-day / closed within ~30 days",
  },
  {
    path: "/auctions/aluminium-scrap/",
    note: "HTML landing with auction cards in raw HTML",
  },
  {
    path: "/auctions/closing-soon/",
    note: "HTML landing — closing within ~72h",
  },
  {
    path: "/auctions/large-scrap-lots/",
    note: "HTML landing — large quantity lots",
  },
  {
    path: "/auctions/llms.txt",
    note: "Short agent overview",
  },
  {
    path: "/auctions/machine-sitemap.xml",
    note: "Machine URL list (not in Google HTML sitemap)",
  },
  {
    path: "/auctions/sitemap.xml",
    note: "HTML sitemap index only",
  },
] as const;

export default function DevelopersPage() {
  return (
    <AppShell>
      <main className="container-marketplace space-y-8 py-10">
        <header className="max-w-3xl space-y-3">
          <h1 className="text-display text-foreground">Developers &amp; agents</h1>
          <p className="text-body text-muted-foreground">{DESCRIPTION}</p>
        </header>

        <section className="max-w-3xl space-y-3" aria-labelledby="consume-heading">
          <h2 id="consume-heading" className="text-heading text-foreground">
            How to consume this site
          </h2>
          <ol className="list-decimal space-y-2 pl-5 text-body text-muted-foreground">
            <li>
              Read{" "}
              <a className="link-action" href="/auctions/llms.txt">
                /auctions/llms.txt
              </a>{" "}
              then{" "}
              <a className="link-action" href="/auctions/api/manifest.json">
                /auctions/api/manifest.json
              </a>
              .
            </li>
            <li>
              Filter with{" "}
              <a className="link-action" href="/auctions/api/latest.json">
                latest
              </a>
              ,{" "}
              <a className="link-action" href="/auctions/api/archive/latest.json">
                archive
              </a>
              ,{" "}
              <a className="link-action" href="/auctions/api/closing-soon.json">
                closing-soon
              </a>
              , or{" "}
              <a className="link-action" href="/auctions/feeds/large-lots.csv">
                large-lots.csv
              </a>
              .
            </li>
            <li>
              Fetch one listing at{" "}
              <code className="text-body-sm">
                /auctions/api/auction/&#123;source&#125;/&#123;id&#125;.json
              </code>
              .
            </li>
            <li>
              Use{" "}
              <a className="link-action" href="/auctions/sitemap.xml">
                /auctions/sitemap.xml
              </a>{" "}
              only for HTML page discovery (never for /api or /feeds).
            </li>
          </ol>
        </section>

        <section className="max-w-3xl space-y-3" aria-labelledby="endpoints-heading">
          <h2 id="endpoints-heading" className="text-heading text-foreground">
            Endpoints
          </h2>
          <ul className="space-y-3">
            {ENDPOINTS.map((ep) => (
              <li key={ep.path} className="border-b border-border pb-3">
                <p className="font-mono text-body-sm text-foreground">{ep.path}</p>
                <p className="text-body-sm text-muted-foreground">{ep.note}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="max-w-3xl space-y-3" aria-labelledby="rules-heading">
          <h2 id="rules-heading" className="text-heading text-foreground">
            Rules
          </h2>
          <ul className="list-disc space-y-2 pl-5 text-body text-muted-foreground">
            <li>
              Bulk app export under{" "}
              <code className="text-body-sm">/auctions/data/</code> is blocked
              for crawlers — use /api and /feeds instead.
            </li>
            <li>
              Machine JSON covers indexable auctions only and strips missing
              local asset paths.
            </li>
            <li>
              Bidding and payment happen only on MSTC, GeM Forward, or
              eAuction.gov.in — this site is discovery research.
            </li>
            <li>
              Search and AI crawlers (including GPTBot / ClaudeBot) are allowed
              on /auctions/ by design; see robots.txt and llms.txt.
            </li>
          </ul>
        </section>
      </main>
      <SiteFooter />
    </AppShell>
  );
}
