"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { enrichAuctions } from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import { auctionDetailPath } from "@/lib/seo/auction-url";
import { trackEvent } from "@/lib/analytics";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
const MapView = dynamic(
  () => import("@/components/map-view").then((m) => m.MapView),
  {
    ssr: false,
    loading: () => <p className="text-muted-foreground">Loading map…</p>,
  },
);
export function MapPageApp() {
  const [auctions, setAuctions] = useState<AuctionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    trackEvent("map_view", { page: "map" });
    loadAuctionsExport()
      .then((d) => setAuctions(enrichAuctions(d.auctions)))
      .finally(() => setLoading(false));
  }, []);
  const discoverHref = resolveAppPath("");
  return (
    <AppShell>
      {" "}
      <main className="container-marketplace space-y-4 py-section">
        {" "}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {" "}
          <div>
            {" "}
            <h1 className="text-display text-foreground">Auction map</h1>{" "}
            <p className="text-body text-muted-foreground">
              City clusters from normalized locations.
            </p>{" "}
          </div>{" "}
          <Link href={discoverHref} className="btn-secondary text-sm">
            Browse auctions
          </Link>
        </div>{" "}
        {loading ? (
          <div
            className="surface-elevated animate-pulse p-4"
            style={{ minHeight: 360 }}
            aria-hidden
          >
            <div className="mb-4 h-5 w-1/3 rounded bg-muted" />
            <div className="h-full min-h-[280px] rounded-lg bg-muted" />
          </div>
        ) : (
          <MapView
            auctions={auctions}
            onSelectAuction={(id) => {
              const auction = auctions.find((a) => a.id === id);
              if (auction) {
                window.location.href = resolvePublicUrl(
                  auctionDetailPath(auction),
                );
              }
            }}
          />
        )}{" "}
        <SiteFooter />{" "}
      </main>{" "}
    </AppShell>
  );
}
