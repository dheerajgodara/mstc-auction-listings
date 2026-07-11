import { absoluteUrl } from "@/lib/site-url";
import { auctionCanonicalUrl } from "@/lib/seo/auction-url";
import { isActiveOrUpcomingClosing } from "@/lib/seo/index-policy";
import { deriveRouteId } from "@/lib/seo/route-id";
import { sourceToSlug } from "@/lib/seo/source-slug";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { sourceLabel } from "@/lib/source-styles";
import type { AuctionRecord } from "@/types/auction";
type JsonLdObject = Record<string, unknown>;
function placeFromAuction(auction: AuctionRecord): JsonLdObject | undefined {
  const city = auction.display_location_city?.trim();
  const state = auction.display_location_state?.trim();
  if (!city && !state) return undefined;
  const address: JsonLdObject = {
    "@type": "PostalAddress",
    addressCountry: "IN",
  };
  if (city) address.addressLocality = city;
  if (state) address.addressRegion = state;
  return {
    "@type": "Place",
    name: [city, state].filter(Boolean).join(", "),
    address,
  };
} /** * Event JSON-LD for auction detail pages. * Omits Offer unless floor price is a reliable numeric value. */
export function buildAuctionEventJsonLd(
  auction: AuctionRecord,
): JsonLdObject | null {
  const enriched = enrichAuctionDisplay(auction);
  const name = enriched.display_title?.trim() || enriched.item_summary?.trim();
  if (!name) return null;
  const active = isActiveOrUpcomingClosing(enriched.closing);
  const event: JsonLdObject = {
    "@context": "https://schema.org",
    "@type": "Event",
    name,
    url: auctionCanonicalUrl(enriched),
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    eventStatus: active
      ? "https://schema.org/EventScheduled"
      : "https://schema.org/EventCancelled",
  };
  if (enriched.opening) event.startDate = enriched.opening;
  if (enriched.closing) event.endDate = enriched.closing;
  const location = placeFromAuction(enriched);
  if (location) event.location = location;
  const floor = enriched.min_start_price;
  if (floor != null && floor > 0) {
    event.offers = {
      "@type": "Offer",
      price: floor,
      priceCurrency: "INR",
      availability: active
        ? "https://schema.org/InStock"
        : "https://schema.org/OutOfStock",
      url: auctionCanonicalUrl(enriched),
    };
  }
  if (enriched.seller?.trim()) {
    event.organizer = { "@type": "Organization", name: enriched.seller.trim() };
  }
  return event;
}
export type BreadcrumbItem = {
  name: string;
  path?: string;
}; /** BreadcrumbList JSON-LD. Last item may omit URL (current page). */
export function buildBreadcrumbJsonLd(items: BreadcrumbItem[]): JsonLdObject {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      ...(item.path ? { item: absoluteUrl(item.path) } : {}),
    })),
  };
} /** Default breadcrumb trail for an auction detail page. */
export function buildAuctionBreadcrumbJsonLd(
  auction: AuctionRecord,
): JsonLdObject {
  const enriched = enrichAuctionDisplay(auction);
  const sourceSlug = sourceToSlug(enriched.source);
  const routeId = deriveRouteId(enriched);
  const sourceName = sourceLabel(enriched.source);
  return buildBreadcrumbJsonLd([
    { name: "Home", path: "/" },
    { name: "Auctions", path: "/" },
    { name: sourceName, path: `/${sourceSlug}-auctions/` },
    { name: routeId },
  ]);
}
export type ItemListEntry = {
  name: string;
  url: string;
}; /** ItemList JSON-LD for curated landing pages. */
export function buildItemListJsonLd(
  listName: string,
  items: ItemListEntry[],
  pageUrl: string,
): JsonLdObject {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: listName,
    url: pageUrl,
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      url: item.url,
    })),
  };
}
