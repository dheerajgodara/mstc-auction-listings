import type { Metadata } from "next";
import { buildSourceLanding } from "@/lib/seo/landing-pages";
const landing = buildSourceLanding(
  "gem_forward",
  "GeM Forward Auctions | Government e-Auction Listings",
  "Active GeM Forward auction listings with lot details, documents, and official source links.",
  "GeM Forward Auctions on Government e-Marketplace cover surplus assets, scrap, and disposals from government buyers. This page aggregates parsed GeM Forward listings with material summaries, locations, and closing dates.\n\nBidding occurs only on the official GeM portal. Use this page for discovery and due diligence.",
  "/gem-forward-auctions/",
);
export const metadata: Metadata = landing.metadata;
export default function GemForwardAuctionsPage() {
  return landing.page;
}
