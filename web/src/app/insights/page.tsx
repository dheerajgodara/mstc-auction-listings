import type { Metadata } from "next";
import { InsightsPageApp } from "@/components/insights-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export const metadata: Metadata = {
  title: "Market insights",
  description: "Auction volume pulse by material, city, and source.",
  ...NOINDEX_METADATA,
};
export default function InsightsPage() {
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <InsightsPageApp />{" "}
    </div>
  );
}
