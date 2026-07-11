import type { Metadata } from "next";
import { PricingPageApp } from "@/components/pricing-page-app";
import { absoluteUrl } from "@/lib/site-url";

const PRICING_CANONICAL = absoluteUrl("pricing/");
const PRICING_DESCRIPTION =
  "Early-access plans for scrap auction discovery — Free, Pro, Trader, Team, and Enterprise. Official source links stay free.";

export const metadata: Metadata = {
  title: "Pricing | Scrap Auction India",
  description: PRICING_DESCRIPTION,
  robots: { index: true, follow: true },
  alternates: { canonical: PRICING_CANONICAL },
  openGraph: {
    title: "Pricing | Scrap Auction India",
    description: PRICING_DESCRIPTION,
    url: PRICING_CANONICAL,
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Pricing | Scrap Auction India",
    description: PRICING_DESCRIPTION,
  },
};

export default function PricingPage() {
  return <PricingPageApp showHeader />;
}
