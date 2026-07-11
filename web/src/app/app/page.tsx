import type { Metadata } from "next";
import { AppInstallPageApp } from "@/components/app-install-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata: Metadata = {
  title: "Install App | Scrap Auction India",
  description:
    "Install Scrap Auction India as an app-style shortcut for watchlists, saved searches, and auction diligence.",
  ...NOINDEX_METADATA,
};

export default function AppPage() {
  return (
    <div className="surface-base min-h-screen">
      <AppInstallPageApp />
    </div>
  );
}
