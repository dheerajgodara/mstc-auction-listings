import type { Metadata } from "next";
import { InsightsPageApp } from "@/components/insights-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export const metadata: Metadata = {
  title: "Catalog pulse",
  description: "Ops-only export volume and document completeness pulse.",
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
