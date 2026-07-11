"use client";

import { useEffect, useState } from "react";
import { AuctionDiscoveryView } from "@/components/auction-discovery-view";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { enrichAuctions } from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import { trackPageView } from "@/lib/analytics";
import { formatDateTime } from "@/lib/utils";
import type { AuctionsExport } from "@/types/auction";

export function AuctionListingsApp() {
  const [data, setData] = useState<AuctionsExport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    trackPageView("/auctions/");
  }, []);

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
          setError(
            err instanceof Error ? err.message : "Failed to load auctions",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const freshnessLabel = data?.automation_ran_at
    ? `Updated ${formatDateTime(data.automation_ran_at)}`
    : undefined;

  if (error) {
    return (
      <AppShell>
        <div className="container-marketplace py-section text-center">
          <p className="text-headline text-foreground">
            Could not load auction data
          </p>
          <p className="mt-2 text-body text-muted-foreground">{error}</p>
        </div>
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell>
        <div className="container-marketplace py-section text-center">
          <p className="text-body text-muted-foreground">Loading auctions…</p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell
      freshnessLabel={freshnessLabel}
      onOpenSearch={() => setPaletteOpen(true)}
    >
      <AuctionDiscoveryView
        auctions={data.auctions}
        generatedAt={data.export_generated_at ?? data.generated_at}
        automationRanAt={data.automation_ran_at ?? undefined}
        total={data.count}
        paletteOpen={paletteOpen}
        onPaletteOpenChange={setPaletteOpen}
      />
      <SiteFooter automationRanAt={data.automation_ran_at ?? undefined} />
    </AppShell>
  );
}
