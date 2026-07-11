import {
  enrichAuctionDisplay,
  MATERIAL_CATEGORY_LABELS,
} from "@/lib/display-enrichment";
import { deriveRouteId } from "@/lib/seo/route-id";
import { sourceLabel } from "@/lib/source-styles";
import { formatDateTime } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
const TITLE_MAX = 60;
const DESCRIPTION_MAX = 160;
function truncate(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max - 1).trimEnd()}…`;
}
function locationPhrase(auction: AuctionRecord): string | null {
  const city = auction.display_location_city?.trim();
  const state = auction.display_location_state?.trim();
  if (city && state) return `${city}, ${state}`;
  return city ?? state ?? auction.state?.trim() ?? null;
}
function materialLabel(auction: AuctionRecord): string | null {
  const key = auction.display_material_category;
  if (!key) return null;
  return (
    MATERIAL_CATEGORY_LABELS[key as keyof typeof MATERIAL_CATEGORY_LABELS] ??
    key
  );
}
function auctionRef(auction: AuctionRecord): string {
  return deriveRouteId(auction);
} /** SERP title from enriched display fields. */
export function buildAuctionTitle(auction: AuctionRecord): string {
  const enriched = enrichAuctionDisplay(auction);
  const title =
    enriched.display_title?.trim() ||
    enriched.item_summary?.trim() ||
    "Auction listing";
  const location = locationPhrase(enriched);
  const source = sourceLabel(enriched.source);
  const ref = auctionRef(enriched);
  const parts: string[] = [];
  if (location) {
    parts.push(`${title} in ${location}`);
  } else {
    parts.push(title);
  }
  parts.push(`${source} ${ref}`);
  return truncate(parts.join(" | "), TITLE_MAX);
} /** Unique meta description from display enrichment. */
export function buildAuctionDescription(auction: AuctionRecord): string {
  const enriched = enrichAuctionDisplay(auction);
  const source = sourceLabel(enriched.source);
  const location = locationPhrase(enriched);
  const material = materialLabel(enriched);
  const closing = enriched.closing ? formatDateTime(enriched.closing) : null;
  const qty = enriched.display_quantity_summary?.trim();
  const bits: string[] = [];
  bits.push(`${source} auction listing`);
  if (material) bits.push(material);
  if (qty) bits.push(qty);
  if (location) bits.push(`in ${location}`);
  if (closing) bits.push(`closes ${closing}`);
  if (enriched.display_buyer_summary?.trim()) {
    bits.push(enriched.display_buyer_summary.trim());
  } else if (enriched.min_start_price != null && enriched.min_start_price > 0) {
    bits.push(
      `floor price from ₹${Math.round(enriched.min_start_price).toLocaleString("en-IN")}`,
    );
  }
  bits.push("Verify on the official source before bidding.");
  return truncate(bits.join(". ").replace(/\.\s*\./g, "."), DESCRIPTION_MAX);
}
