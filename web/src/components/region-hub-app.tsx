"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { AuctionDiscoveryView } from "@/components/auction-discovery-view";
import { SiteFooter } from "@/components/site-footer";
import { enrichAuctionDisplay, enrichAuctions } from "@/lib/display-enrichment";
import { loadAuctionsExport } from "@/lib/load-auctions";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";

const REGION_PRESETS: Record<
  string,
  { title: string; states: string[]; cities?: string[] }
> = {
  ncr: {
    title: "NCR & North India",
    states: ["Delhi", "Haryana", "Uttar Pradesh", "Rajasthan"],
  },
  mumbai: {
    title: "Mumbai & Maharashtra",
    states: ["Maharashtra"],
    cities: ["Mumbai", "Navi Mumbai", "Pune"],
  },
  bengaluru: {
    title: "Bengaluru & Karnataka",
    states: ["Karnataka"],
    cities: ["Bengaluru", "Mysuru"],
  },
  chennai: {
    title: "Chennai & Tamil Nadu",
    states: ["Tamil Nadu"],
    cities: ["Chennai"],
  },
  hyderabad: {
    title: "Hyderabad & Telangana",
    states: ["Telangana", "Andhra Pradesh"],
    cities: ["Hyderabad"],
  },
  kolkata: {
    title: "Kolkata & East",
    states: ["West Bengal", "Odisha", "Bihar", "Jharkhand"],
  },
};

export function RegionHubApp({ slug }: { slug: string }) {
  const preset = REGION_PRESETS[slug] ?? { title: slug, states: [] };
  const [all, setAll] = useState<AuctionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    loadAuctionsExport()
      .then((d) => setAll(enrichAuctions(d.auctions)))
      .finally(() => setLoading(false));
  }, []);
  const filtered = useMemo(() => {
    return all.filter((a) => {
      const st =
        enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
      const city = enrichAuctionDisplay(a).display_location_city ?? "";
      if (preset.states.some((s) => st.includes(s))) return true;
      if (
        preset.cities?.some((c) => city.toLowerCase().includes(c.toLowerCase()))
      )
        return true;
      return false;
    });
  }, [all, preset]);
  return (
    <AppShell>
      <main className="py-section">
        <div className="container-marketplace mb-4 space-y-2">
          <Link href={resolveAppPath("map/")} className="text-body-sm link-action">
            View map
          </Link>
          <h1 className="text-display text-foreground">{preset.title}</h1>
          <p className="text-body text-muted-foreground">
            {filtered.length} auctions in this hub filter.
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
