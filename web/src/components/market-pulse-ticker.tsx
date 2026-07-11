"use client";
import { useMemo } from "react";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { formatCountdown, parseClosingMs } from "@/lib/auction-filters";
import type { AuctionRecord } from "@/types/auction";
export function MarketPulseTicker({ auctions }: { auctions: AuctionRecord[] }) {
  const message = useMemo(() => {
    const now = Date.now();
    const closingSoon = auctions
      .map((a) => ({ a, ms: parseClosingMs(a.closing) }))
      .filter(
        (x) => x.ms !== null && x.ms > now && x.ms - now < 6 * 60 * 60 * 1000,
      )
      .sort((x, y) => (x.ms ?? 0) - (y.ms ?? 0))[0];
    if (closingSoon) {
      const e = enrichAuctionDisplay(closingSoon.a);
      const title = (e.display_title ?? e.auction_number).slice(0, 48);
      return (
        <>
          {" "}
          Closing soon:{" "}
          <strong className="font-medium text-foreground">
            {title}
          </strong> — {formatCountdown(closingSoon.ms!)} left.{" "}
          <span className="text-muted-foreground">
            Verify on the official source before bidding.
          </span>{" "}
        </>
      );
    }
    const todayImports = auctions.filter((a) => {
      const iso = a.imported_at ?? a.first_seen_at;
      if (!iso) return false;
      return new Date(iso).toDateString() === new Date().toDateString();
    }).length;
    if (todayImports > 0) {
      return `${todayImports} new imports today across MSTC, GeM, and eAuction.`;
    }
    return `${auctions.length} active listings — search, filter, and open diligence before you bid on official portals.`;
  }, [auctions]);
  return (
    <div
      className="border-y border-border bg-muted/60 py-2.5 text-center text-caption text-muted-foreground"
      aria-live="polite"
    >
      {" "}
      <div className="container-marketplace">{message}</div>{" "}
    </div>
  );
}
