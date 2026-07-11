import type { Metadata } from "next";
import { Suspense } from "react";
import { AccountPageApp } from "@/components/account-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata: Metadata = {
  title: "Account | Scrap Auction India",
  description: "Account and subscription status (early access).",
  ...NOINDEX_METADATA,
};

export default function AccountPage() {
  return (
    <div className="surface-base min-h-screen">
      <Suspense fallback={null}>
        <AccountPageApp />
      </Suspense>
    </div>
  );
}
