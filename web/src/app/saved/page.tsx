import type { Metadata } from "next";
import { SavedPageApp } from "@/components/saved-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export const metadata: Metadata = {
  title: "Saved searches",
  description: "Manage saved auction discovery searches.",
  ...NOINDEX_METADATA,
};
export default function SavedPage() {
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <SavedPageApp />{" "}
    </div>
  );
}
