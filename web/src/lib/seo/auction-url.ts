import { absoluteUrl } from "@/lib/site-url";
import { deriveRouteId } from "@/lib/seo/route-id";
import { sourceToSlug } from "@/lib/seo/source-slug";
import type { AuctionRecord } from "@/types/auction";
export function auctionDetailPath(auction: AuctionRecord): string {
  const sourceSlug = sourceToSlug(auction.source);
  const routeId = deriveRouteId(auction);
  return `/${sourceSlug}/${routeId}/`;
} /** Canonical absolute URL for an auction detail page. */
export function auctionCanonicalUrl(auction: AuctionRecord): string {
  return absoluteUrl(auctionDetailPath(auction));
}
export function buildTopDetailLinks(auctions: AuctionRecord[], limit = 12) {
  return auctions.slice(0, limit).map((a) => ({
    label: a.display_title?.slice(0, 50) || a.auction_number,
    href: auctionCanonicalUrl(a),
  }));
}
