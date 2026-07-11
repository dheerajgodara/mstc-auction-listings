"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { AuctionCard } from "@/components/auction-card";
import { AuctionCardSkeleton } from "@/components/auction-card-skeleton";
import { SiteFooter } from "@/components/site-footer";
import { useUpgradePrompt } from "@/components/upgrade-prompt";
import { enrichAuctions } from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import { getPlanCaps, getCurrentPlan } from "@/lib/entitlements";
import { loadWatchlist, tryToggleWatchlist } from "@/lib/watchlist";
import { auctionDetailPath } from "@/lib/seo/auction-url";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
export function WatchlistPageApp() {
  const [auctions, setAuctions] = useState<AuctionRecord[]>([]);
  const [watchlist, setWatchlist] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);
  const { gateFeature } = useUpgradePrompt();
  const caps = getPlanCaps(getCurrentPlan());
  useEffect(() => {
    setWatchlist(loadWatchlist());
    loadAuctionsExport()
      .then((d) => setAuctions(enrichAuctions(d.auctions)))
      .finally(() => setLoading(false));
  }, []);
  const starred = useMemo(
    () => auctions.filter((a) => watchlist.has(a.id)),
    [auctions, watchlist],
  );
  return (
    <AppShell>
      {" "}
      <main className="container-marketplace space-y-4 py-section">
        {" "}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {" "}
          <div>
            {" "}
            <h1 className="text-display text-foreground">Watchlist</h1>{" "}
            <p className="text-body-sm">
              {starred.length} saved auctions (stored on this device). Limit:{" "}
              {caps.watchlist}.
            </p>{" "}
          </div>{" "}
          <Link href={resolveAppPath("")} className="btn-primary text-sm">
              {" "}
              Discover more{" "}
            </Link>{" "}
          </div>{" "}
        {loading ? (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <AuctionCardSkeleton key={i} />
            ))}
          </div>
        ) : starred.length === 0 ? (
          <div className="surface-elevated p-8 text-center">
            <p className="text-title text-foreground">No starred auctions yet</p>
            <p className="mt-2 text-body-sm text-muted-foreground">
              Tap the star on any card in Discover to build your watchlist.
            </p>
            <Link
              href={resolveAppPath("")}
              className="btn-primary mt-6 inline-flex text-sm"
            >
              Discover auctions
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {" "}
            {starred.map((auction, i) => (
              <AuctionCard
                key={auction.id}
                auction={auction}
                index={i}
                watched
                onToggleWatch={(id) => {
                  const result = tryToggleWatchlist(id);
                  if (!result.ok) {
                    gateFeature("watchlist_add", false, "watchlist_page");
                    return;
                  }
                  setWatchlist(result.watchlist);
                }}
                onOpenDiligence={() => {
                  window.location.href = resolvePublicUrl(
                    auctionDetailPath(auction),
                  );
                }}
              />
            ))}{" "}
          </div>
        )}{" "}
        <SiteFooter />{" "}
      </main>{" "}
    </AppShell>
  );
}
