import type { AuctionRecord } from "@/types/auction";
import { sourceToSlug } from "@/lib/seo/source-slug";
const ROUTE_ID_SAFE =
  /^[a-zA-Z0-9._-]+$/; /** * Derive a path-safe, stable route_id for auction detail URLs. * Strips internal source prefixes (e.g. `gem_forward:36121` → `36121`). */
export function deriveRouteId(auction: AuctionRecord): string {
  const source = auction.source ?? "mstc";
  let raw =
    auction.source_auction_id?.trim() ||
    auction.auction_number?.trim() ||
    auction.id?.trim() ||
    "";
  const sourcePrefix = `${source}:`;
  if (auction.id?.startsWith(sourcePrefix)) {
    raw = auction.id.slice(sourcePrefix.length);
  } else if (raw.includes(":")) {
    const colonIdx = raw.indexOf(":");
    raw = raw.slice(colonIdx + 1);
  }
  raw = raw.trim();
  if (!raw) {
    raw = (auction.id ?? "unknown").replace(/^[^:]+:/, "");
  }
  return encodeRouteIdSegment(raw);
}
function encodeRouteIdSegment(value: string): string {
  if (ROUTE_ID_SAFE.test(value)) return value;
  return value
    .split("")
    .map((ch) => (ROUTE_ID_SAFE.test(ch) ? ch : encodeURIComponent(ch)))
    .join("");
} /** Composite lookup key for `{source_slug}/{route_id}` route pairs. */
export function buildRouteKey(sourceSlug: string, routeId: string): string {
  return `${sourceSlug}/${routeId}`;
} /** Route key for an auction record. */
export function auctionRouteKey(auction: AuctionRecord): string {
  return buildRouteKey(sourceToSlug(auction.source), deriveRouteId(auction));
}
