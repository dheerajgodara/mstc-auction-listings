import type { Metadata } from "next";
import { MapPageApp } from "@/components/map-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export const metadata: Metadata = {
  title: "Auction Map | City clusters",
  description:
    "Browse government auctions on a map with city clusters and radius filter.",
  ...NOINDEX_METADATA,
};
export default function MapPage() {
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <MapPageApp />{" "}
    </div>
  );
}
