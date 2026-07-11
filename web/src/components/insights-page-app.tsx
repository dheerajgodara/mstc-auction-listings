"use client";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { countAuctionDocuments } from "@/lib/auction-documents";
import { enrichAuctionDisplay, enrichAuctions } from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import { resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
interface InsightsSnapshot {
  generated_at?: string;
  closing_by_week?: Record<string, number>;
  top_cities?: { city: string; count: number }[];
  documents_by_source?: Record<string, { with_docs: number; total: number }>;
}
export function InsightsPageApp() {
  const [auctions, setAuctions] = useState<AuctionRecord[]>([]);
  const [snapshot, setSnapshot] = useState<InsightsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    Promise.all([
      loadAuctionsExport().then((d) => enrichAuctions(d.auctions)),
      fetch(resolvePublicUrl("data/insights.json"), { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ])
      .then(([list, snap]) => {
        setAuctions(list);
        setSnapshot(snap);
      })
      .finally(() => setLoading(false));
  }, []);
  const computed = useMemo(() => {
    const bySource: Record<string, { with_docs: number; total: number }> = {};
    const cityCounts = new Map<string, number>();
    for (const a of auctions) {
      const src = a.source ?? "mstc";
      if (!bySource[src]) bySource[src] = { with_docs: 0, total: 0 };
      bySource[src].total += 1;
      const docs = countAuctionDocuments(a);
      if (docs.documents > 0 || docs.photos > 0) bySource[src].with_docs += 1;
      const city = enrichAuctionDisplay(a).display_location_city;
      if (city) cityCounts.set(city, (cityCounts.get(city) ?? 0) + 1);
    }
    const topCities = [...cityCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([city, count]) => ({ city, count }));
    return { bySource, topCities };
  }, [auctions]);
  const data = snapshot ?? {
    top_cities: computed.topCities,
    documents_by_source: computed.bySource,
  };
  return (
    <AppShell>
      {" "}
      <main className="container-marketplace space-y-6 py-section">
        {" "}
        <div>
          {" "}
          <h1 className="text-display text-foreground">Market insights</h1>{" "}
          <p className="text-body-sm">
            {" "}
            Client-computed pulse from the current export{" "}
            {data.generated_at ? ` · ${data.generated_at}` : ""}.{" "}
          </p>{" "}
        </div>{" "}
        {loading ? (
          <div className="grid gap-4 md:grid-cols-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="surface-elevated animate-pulse space-y-3 p-4"
                aria-hidden
              >
                <div className="h-5 w-1/2 rounded bg-muted" />
                <div className="h-4 w-full rounded bg-muted" />
                <div className="h-4 w-3/4 rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {" "}
            <section className="surface-elevated p-4">
              {" "}
              <h2 className="text-heading mb-3">Top cities by volume</h2>{" "}
              <ul className="space-y-2 text-sm">
                {" "}
                {(data.top_cities ?? computed.topCities).map((row) => (
                  <li key={row.city} className="flex justify-between gap-2">
                    {" "}
                    <span>{row.city}</span>{" "}
                    <span className="tabular-nums font-medium">
                      {row.count}
                    </span>{" "}
                  </li>
                ))}{" "}
              </ul>{" "}
            </section>{" "}
            <section className="surface-elevated p-4">
              {" "}
              <h2 className="text-heading mb-3">
                Document completeness by source
              </h2>{" "}
              <ul className="space-y-2 text-sm">
                {" "}
                {Object.entries(
                  data.documents_by_source ?? computed.bySource,
                ).map(([src, stats]) => (
                  <li key={src} className="flex justify-between gap-2">
                    {" "}
                    <span className="uppercase">
                      {src.replace(/_/g, " ")}
                    </span>{" "}
                    <span className="tabular-nums">
                      {" "}
                      {stats.with_docs}/{stats.total}{" "}
                    </span>{" "}
                  </li>
                ))}{" "}
              </ul>{" "}
            </section>{" "}
            <section className="surface-elevated p-4 md:col-span-2">
              {" "}
              <h2 className="text-heading mb-2">Total active listings</h2>{" "}
              <p className="text-3xl font-bold tabular-nums text-action">
                {auctions.length}
              </p>{" "}
            </section>{" "}
          </div>
        )}{" "}
        <SiteFooter />{" "}
      </main>{" "}
    </AppShell>
  );
}
