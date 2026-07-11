import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SeoLandingPage } from "@/components/seo-landing-page";
import { buildTopDetailLinks } from "@/lib/seo/auction-url";
import { loadAuctionsAtBuild } from "@/lib/load-auction-at-build";
import { landingPageQualifies } from "@/lib/seo/index-policy";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
import { absoluteUrl } from "@/lib/site-url";
import type { AuctionRecord, AuctionSource } from "@/types/auction";
export function buildSourceLanding(
  source: AuctionSource,
  title: string,
  description: string,
  intro: string,
  path: string,
): { page: ReactNode; metadata: Metadata } {
  const data = loadAuctionsAtBuild();
  const auctions = (data.auctions ?? []).filter(
    (a) => (a.source ?? "mstc") === source,
  );
  const indexable = landingPageQualifies(auctions.length, 10);
  const metadata: Metadata = {
    title,
    description,
    alternates: { canonical: absoluteUrl(path) },
    robots: indexable ? { index: true, follow: true } : NOINDEX_METADATA.robots,
  };
  return {
    metadata,
    page: (
      <SeoLandingPage
        title={title}
        description={description}
        intro={intro}
        auctions={auctions}
        topLinks={buildTopDetailLinks(auctions)}
        landingSlug={path.replace(/^\/|\/$/g, "")}
      />
    ),
  };
}
export function filterAuctions(
  predicate: (a: AuctionRecord) => boolean,
): AuctionRecord[] {
  return (loadAuctionsAtBuild().auctions ?? []).filter(predicate);
}
