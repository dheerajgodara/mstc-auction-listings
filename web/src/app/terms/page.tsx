import type { Metadata } from "next";
import { LegalPageApp } from "@/components/legal-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata: Metadata = {
  title: "Terms of use | Scrap Auction India",
  description: "Terms of use for the auction discovery site.",
  ...NOINDEX_METADATA,
};

export default function TermsPage() {
  return (
    <div className="surface-base min-h-screen">
      <LegalPageApp title="Terms of use">
        <p>
          Scrap Auction India is an independent discovery layer over publicly
          listed government and PSU auctions. We do not conduct auctions, hold
          bids, or collect EMD on behalf of buyers.
        </p>
        <p>
          Listings are aggregated from official sources (MSTC, GeM Forward,
          eAuction.gov.in). Buyers must verify all facts, documents, and payment
          instructions on the official portal before bidding.
        </p>
        <p>
          Paid subscriptions, when live, will be governed by a separate order
          form and refund policy. Until billing launches, no charges apply.
        </p>
        <p className="text-footnote">
          Draft for legal review — not final counsel-approved text.
        </p>
      </LegalPageApp>
    </div>
  );
}
