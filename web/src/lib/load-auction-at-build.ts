import fs from "node:fs";
import path from "node:path";
import { buildRouteKey, deriveRouteId } from "@/lib/seo/route-id";
import { sourceToSlug, type SourceSlug } from "@/lib/seo/source-slug";
import { isIndexableAuction } from "@/lib/seo/index-policy";
import type { AuctionRecord, AuctionsExport } from "@/types/auction";
export interface AuctionRouteEntry {
  id: string;
  route_id: string;
  source_slug: SourceSlug;
  lastmod?: string;
  indexable?: boolean;
  title_hint?: string | null;
}
export interface AuctionRoutesExport {
  generated_at?: string;
  automation_ran_at?: string;
  count: number;
  routes: AuctionRouteEntry[];
}
export interface StaticRouteParam {
  source: string;
  id: string;
}
const DATA_DIR = path.join(process.cwd(), "public", "data");
const AUCTIONS_PATH = path.join(DATA_DIR, "auctions.json");
const ROUTES_PATH = path.join(DATA_DIR, "auction-routes.json");
let cachedExport: AuctionsExport | null = null;
let cachedRoutes: AuctionRoutesExport | null = null;
let routeByKey: Map<string, AuctionRouteEntry> | null = null;
let auctionById: Map<string, AuctionRecord> | null = null;
function readJsonFile<T>(filePath: string): T {
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
}
function loadAuctionsExport(): AuctionsExport {
  if (cachedExport) return cachedExport;
  if (!fs.existsSync(AUCTIONS_PATH)) {
    throw new Error(`Missing auctions data at ${AUCTIONS_PATH}`);
  }
  cachedExport = readJsonFile<AuctionsExport>(AUCTIONS_PATH);
  return cachedExport;
}
function buildRoutesFromAuctions(
  exportData: AuctionsExport,
): AuctionRoutesExport {
  const routes: AuctionRouteEntry[] = (exportData.auctions ?? []).map(
    (auction) => {
      const source_slug = sourceToSlug(auction.source);
      const route_id = deriveRouteId(auction);
      const lastmod =
        auction.last_seen_at ??
        auction.imported_at ??
        auction.first_seen_at ??
        exportData.automation_ran_at ??
        exportData.generated_at;
      return {
        id: auction.id,
        route_id,
        source_slug,
        lastmod: lastmod ?? undefined,
        indexable: isIndexableAuction(auction),
        title_hint: auction.display_title ?? auction.item_summary ?? null,
      };
    },
  );
  return {
    generated_at: exportData.generated_at,
    automation_ran_at: exportData.automation_ran_at ?? undefined,
    count: routes.length,
    routes,
  };
}
function loadRoutesExport(): AuctionRoutesExport {
  if (cachedRoutes) return cachedRoutes;
  if (fs.existsSync(ROUTES_PATH)) {
    cachedRoutes = readJsonFile<AuctionRoutesExport>(ROUTES_PATH);
    return cachedRoutes;
  }
  cachedRoutes = buildRoutesFromAuctions(loadAuctionsExport());
  return cachedRoutes;
}
function ensureIndexes(): void {
  if (routeByKey && auctionById) return;
  const exportData = loadAuctionsExport();
  const routesData = loadRoutesExport();
  auctionById = new Map();
  for (const auction of exportData.auctions ?? []) {
    auctionById.set(auction.id, auction);
  }
  routeByKey = new Map();
  for (const route of routesData.routes ?? []) {
    routeByKey.set(buildRouteKey(route.source_slug, route.route_id), route);
  }
} /** All route entries from `auction-routes.json` (or derived fallback). */
export function getAllRoutes(): AuctionRouteEntry[] {
  ensureIndexes();
  return loadRoutesExport().routes ?? [];
} /** Params for Next.js `generateStaticParams` on `[source]/[id]` pages. */
export function loadRoutesForStaticParams(): StaticRouteParam[] {
  return getAllRoutes().map((route) => ({
    source: route.source_slug,
    id: route.route_id,
  }));
} /** Resolve an auction by URL `{source_slug, route_id}` at build time. */
export function getAuctionByRoute(
  sourceSlug: string,
  routeId: string,
): AuctionRecord | null {
  ensureIndexes();
  const route = routeByKey!.get(buildRouteKey(sourceSlug, routeId));
  if (!route) return null;
  return auctionById!.get(route.id) ?? null;
} /** Lookup a route entry without loading the full auction record. */
export function getRouteEntry(
  sourceSlug: string,
  routeId: string,
): AuctionRouteEntry | null {
  ensureIndexes();
  return routeByKey!.get(buildRouteKey(sourceSlug, routeId)) ?? null;
} /** Full auctions export (build-time only). */
export function loadAuctionsAtBuild(): AuctionsExport {
  return loadAuctionsExport();
}
