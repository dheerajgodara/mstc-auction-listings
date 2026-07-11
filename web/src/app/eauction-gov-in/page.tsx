import type { Metadata } from "next";
import { buildSourceLanding } from "@/lib/seo/landing-pages";
const landing = buildSourceLanding(
  "eauction",
  "eAuction.gov.in Listings | Government Auction India",
  "Public eAuction.gov.in listings with parsed lot data, locations, and closing schedules.",
  "eAuction.gov.in is India's unified government e-auction platform used by ministries, states, and PSUs. This page lists active auctions from public ByDate tabs with parsed titles, locations, and document links.\n\nVerify all details on eAuction.gov.in before bidding. This aggregator is independent and not an official government site.",
  "/eauction-gov-in/",
);
export const metadata: Metadata = landing.metadata;
export default function EAuctionGovInPage() {
  return landing.page;
}
