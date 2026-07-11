"use client";

import type { AuctionRecord } from "@/types/auction";
import { AuctionDiscoveryView } from "@/components/auction-discovery-view";

/** @deprecated Use AuctionDiscoveryView directly. Thin wrapper for SEO landings. */
export function AuctionListings({
  auctions,
  total,
  generatedAt,
  automationRanAt,
  showHomeModules = false,
  showHero = false,
  heroTitle,
  heroDescription,
}: {
  auctions: AuctionRecord[];
  total?: number;
  generatedAt?: string;
  automationRanAt?: string;
  showHomeModules?: boolean;
  showHero?: boolean;
  heroTitle?: string;
  heroDescription?: string;
}) {
  return (
    <AuctionDiscoveryView
      auctions={auctions}
      total={total}
      generatedAt={generatedAt}
      automationRanAt={automationRanAt}
      showHomeModules={showHomeModules}
      showHero={showHero}
      heroTitle={heroTitle}
      heroDescription={heroDescription}
    />
  );
}
