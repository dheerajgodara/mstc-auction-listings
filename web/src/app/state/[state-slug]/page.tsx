import type { Metadata } from "next";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { SeoLandingPage } from "@/components/seo-landing-page";
import { buildTopDetailLinks } from "@/lib/seo/auction-url";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { loadAuctionsAtBuild } from "@/lib/load-auction-at-build";
import { landingPageQualifies } from "@/lib/seo/index-policy";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
import { absoluteUrl } from "@/lib/site-url";
interface StatePageConfig {
  slug: string;
  stateName: string;
  intro: string;
}
function loadStateConfigs(): StatePageConfig[] {
  const p = path.join(process.cwd(), "public", "data", "seo-state-pages.json");
  if (!fs.existsSync(p)) return [];
  return JSON.parse(fs.readFileSync(p, "utf8")) as StatePageConfig[];
}
export function generateStaticParams() {
  const configs = loadStateConfigs();
  const data = loadAuctionsAtBuild();
  return configs
    .filter((cfg) => {
      const count = (data.auctions ?? []).filter((a) => {
        const st =
          enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
        return st.toLowerCase().includes(cfg.stateName.toLowerCase());
      }).length;
      return landingPageQualifies(count, 15);
    })
    .map((cfg) => ({ "state-slug": cfg.slug }));
}
type PageProps = { params: Promise<{ "state-slug": string }> };
export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { "state-slug": slug } = await params;
  const cfg = loadStateConfigs().find((c) => c.slug === slug);
  if (!cfg) return {};
  const data = loadAuctionsAtBuild();
  const auctions = (data.auctions ?? []).filter((a) => {
    const st = enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
    return st.toLowerCase().includes(cfg.stateName.toLowerCase());
  });
  const indexable = landingPageQualifies(auctions.length, 15);
  const title = `${cfg.stateName} Government Auctions | Scrap & Surplus Listings`;
  const description = `Active government auctions in ${cfg.stateName} — MSTC, GeM, and eAuction listings with lot details.`;
  return {
    title,
    description,
    alternates: { canonical: absoluteUrl(`/state/${slug}/`) },
    robots: indexable ? { index: true, follow: true } : NOINDEX_METADATA.robots,
  };
}
export default async function StateLandingPage({ params }: PageProps) {
  const { "state-slug": slug } = await params;
  const cfg = loadStateConfigs().find((c) => c.slug === slug);
  if (!cfg) notFound();
  const data = loadAuctionsAtBuild();
  const auctions = (data.auctions ?? []).filter((a) => {
    const st = enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
    return st.toLowerCase().includes(cfg.stateName.toLowerCase());
  });
  if (!landingPageQualifies(auctions.length, 15)) notFound();
  return (
    <SeoLandingPage
      title={`${cfg.stateName} Auctions`}
      description={`${auctions.length} active government auction listings in ${cfg.stateName}.`}
      intro={`${cfg.intro}\n\nAlways verify on official source portals before bidding.`}
      auctions={auctions}
      topLinks={buildTopDetailLinks(auctions)}
    />
  );
}
