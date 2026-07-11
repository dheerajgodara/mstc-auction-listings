import type { Metadata } from "next";
import { buildSourceLanding } from "@/lib/seo/landing-pages";
const landing = buildSourceLanding(
  "mstc",
  "MSTC Auctions India | Live Government e-Auction Listings",
  "Browse current MSTC e-auction listings for scrap, vehicles, machinery, and minerals across India.",
  "MSTC (Metal Scrap Trade Corporation) hosts government and PSU e-auctions for scrap metal, vehicles, plant machinery, and surplus assets. This page lists active MSTC auctions parsed from public sources with buyer-ready summaries, lot details, and links to official PDFs.\n\nAlways verify lot specifications and closing times on the official MSTC portal before placing bids. This site is for discovery and diligence — not for bidding.",
  "/mstc-auctions/",
);
export const metadata: Metadata = landing.metadata;
export default function MstcAuctionsPage() {
  return landing.page;
}
