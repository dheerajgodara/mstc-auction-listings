import type { Metadata } from "next";
import { SupportPageApp } from "@/components/support-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata: Metadata = {
  title: "Support | Scrap Auction India",
  description: "Buyer support and Enterprise contact.",
  ...NOINDEX_METADATA,
};

export default function SupportPage() {
  return (
    <div className="surface-base min-h-screen">
      <SupportPageApp />
    </div>
  );
}
