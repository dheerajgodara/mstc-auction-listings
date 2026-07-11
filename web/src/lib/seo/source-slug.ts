import type { AuctionSource } from "@/types/auction";
export type SourceSlug = "mstc" | "gem-forward" | "eauction";
const SOURCE_TO_SLUG: Record<AuctionSource, SourceSlug> = {
  mstc: "mstc",
  gem_forward: "gem-forward",
  eauction: "eauction",
};
const SLUG_TO_SOURCE: Record<SourceSlug, AuctionSource> = {
  mstc: "mstc",
  "gem-forward": "gem_forward",
  eauction: "eauction",
}; /** Map internal auction source to URL slug segment. */
export function sourceToSlug(source?: AuctionSource | null): SourceSlug {
  const key = source ?? "mstc";
  return SOURCE_TO_SLUG[key] ?? "mstc";
} /** Map URL slug segment back to internal auction source. */
export function slugToSource(slug: string): AuctionSource | null {
  const normalized = slug.trim().toLowerCase() as SourceSlug;
  return SLUG_TO_SOURCE[normalized] ?? null;
}
export function isValidSourceSlug(slug: string): slug is SourceSlug {
  return slug.trim().toLowerCase() in SLUG_TO_SOURCE;
}
