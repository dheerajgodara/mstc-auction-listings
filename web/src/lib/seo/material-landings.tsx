import type { Metadata } from "next";
import { SeoLandingPage } from "@/components/seo-landing-page";
import { buildTopDetailLinks } from "@/lib/seo/auction-url";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { filterAuctions } from "@/lib/seo/landing-pages";
import { landingPageQualifies } from "@/lib/seo/index-policy";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
import { absoluteUrl } from "@/lib/site-url";
import type { AssetCategory } from "@/types/auction";
const SCRAP_CATEGORIES = new Set<AssetCategory>([
  "scrap",
  "ewaste",
  "minerals",
  "coal",
  "other",
]);
export function buildMaterialLanding(
  path: string,
  title: string,
  description: string,
  intro: string,
  predicate: (a: ReturnType<typeof enrichAuctionDisplay>) => boolean,
) {
  const auctions = filterAuctions((a) => predicate(enrichAuctionDisplay(a)));
  const indexable = landingPageQualifies(auctions.length, 10);
  const metadata: Metadata = {
    title,
    description,
    alternates: { canonical: absoluteUrl(path) },
    robots: indexable ? { index: true, follow: true } : NOINDEX_METADATA.robots,
  };
  const page = (
    <SeoLandingPage
      title={title}
      description={description}
      intro={intro}
      auctions={auctions}
      topLinks={buildTopDetailLinks(auctions)}
      landingSlug={path.replace(/^\/|\/$/g, "")}
    />
  );
  return { metadata, page };
}
