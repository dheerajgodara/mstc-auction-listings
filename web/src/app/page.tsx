import type { Metadata } from "next";
import { AuctionListingsApp } from "@/components/auction-listings-app";

export const metadata: Metadata = {
  title: "Scrap Auction India | MSTC, GeM & eAuction Listings",
  description:
    "Search and filter scrap auction listings across MSTC, GeM Forward, and eAuction.gov.in with import dates, documents, and buyer-ready summaries.",
};

export default function HomePage() {
  return <AuctionListingsApp />;
}
