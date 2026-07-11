import type { Metadata } from "next";
import { WatchlistPageApp } from "@/components/watchlist-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export const metadata: Metadata = {
  title: "Watchlist | Saved auctions",
  description: "Your starred government auction listings.",
  ...NOINDEX_METADATA,
};
export default function WatchlistPage() {
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <WatchlistPageApp />{" "}
    </div>
  );
}
