import type { Metadata } from "next";
import { LegalPageApp } from "@/components/legal-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata: Metadata = {
  title: "Privacy policy | Scrap Auction India",
  description: "Privacy policy for the auction discovery site.",
  ...NOINDEX_METADATA,
};

export default function PrivacyPage() {
  return (
    <div className="surface-base min-h-screen">
      <LegalPageApp title="Privacy policy">
        <p>
          We collect minimal analytics (page views and product events) when Google
          Analytics is enabled. Watchlists, saved searches, and notes are stored
          locally in your browser unless and until account sync ships.
        </p>
        <p>
          We do not collect passwords or payment card data on this static site.
          Future billing will use a certified payment provider with its own
          privacy terms.
        </p>
        <p>
          Official PDFs and source portals are third-party sites with separate
          privacy practices.
        </p>
        <p className="text-footnote">
          Draft for legal review — not final counsel-approved text.
        </p>
      </LegalPageApp>
    </div>
  );
}
