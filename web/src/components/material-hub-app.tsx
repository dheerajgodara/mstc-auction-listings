"use client";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { AuctionDiscoveryView } from "@/components/auction-discovery-view";
import { SiteFooter } from "@/components/site-footer";
import {
  DISPLAY_MATERIAL_CATEGORIES,
  enrichAuctionDisplay,
  enrichAuctions,
  materialCategoryLabel,
} from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import type { AuctionRecord } from "@/types/auction";

export function MaterialHubApp({ materialId }: { materialId: string }) {
  const [all, setAll] = useState<AuctionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const label =
    DISPLAY_MATERIAL_CATEGORIES.find((m) => m.id === materialId)?.label ??
    materialCategoryLabel(materialId) ??
    materialId;
  useEffect(() => {
    loadAuctionsExport()
      .then((d) => setAll(enrichAuctions(d.auctions)))
      .finally(() => setLoading(false));
  }, []);
  const filtered = useMemo(
    () =>
      all.filter(
        (a) => enrichAuctionDisplay(a).display_material_category === materialId,
      ),
    [all, materialId],
  );
  return (
    <AppShell>
      <main className="py-section">
        <div className="container-marketplace mb-4 space-y-2">
          <h1 className="text-display text-foreground">{label}</h1>
          <p className="text-body text-muted-foreground">
            {loading
              ? "Loading auctions…"
              : `${filtered.length} auctions with this material category.`}
          </p>
        </div>
        {loading ? (
          <p className="container-marketplace text-center text-muted-foreground">
            Loading…
          </p>
        ) : (
          <AuctionDiscoveryView
            auctions={filtered}
            total={filtered.length}
            showHomeModules={false}
            showHero={false}
          />
        )}
        <SiteFooter />
      </main>
    </AppShell>
  );
}
