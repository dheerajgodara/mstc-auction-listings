"use client";

import { useEffect, useState } from "react";
import { AuctionListings } from "@/components/auction-listings";
import { enrichAuctions } from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import type { AuctionsExport } from "@/types/auction";

export function AuctionListingsApp() {
  const [data, setData] = useState<AuctionsExport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadAuctionsExport()
      .then((exportData) => {
        if (!cancelled) {
          setData({
            ...exportData,
            auctions: enrichAuctions(exportData.auctions),
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load auctions");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl p-8 text-center">
        <p className="text-lg font-semibold text-rose-800">Could not load auction data</p>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-2xl p-12 text-center">
        <p className="text-slate-600">Loading auctions…</p>
      </div>
    );
  }

  return (
    <AuctionListings
      auctions={data.auctions}
      generatedAt={data.export_generated_at ?? data.generated_at}
      automationRanAt={data.automation_ran_at ?? undefined}
      total={data.count}
    />
  );
}
