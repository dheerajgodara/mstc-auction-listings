import type { Metadata } from "next";
import { AuctionListingsApp } from "@/components/auction-listings-app";

export const metadata: Metadata = {
  title: "Government Auction Listings | MSTC",
  description: "Search current and forthcoming MSTC e-auctions across India",
};

export default function HomePage() {
  return (
    <div className="page-bg">
      <div
        className="pointer-events-none fixed inset-0 -z-10 page-bg-grid"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_20%_0%,rgba(56,189,248,0.18),transparent_45%)]"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_90%_80%,rgba(167,139,250,0.12),transparent_40%)]"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_50%_100%,rgba(134,239,172,0.15),transparent_45%)]"
        aria-hidden
      />
      <main className="relative min-h-screen px-4 py-4 sm:px-6">
        <AuctionListingsApp />
      </main>
    </div>
  );
}
