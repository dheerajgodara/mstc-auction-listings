import type { AuctionRecord } from "@/types/auction";
function escapeIcsText(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\n/g, "\\n");
}
function formatIcsUtc(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "Z");
}
function auctionSummary(auction: AuctionRecord): string {
  return (
    auction.display_title ??
    auction.item_summary ??
    `Auction ${auction.auction_number}`
  );
}
function buildEvent(auction: AuctionRecord, index: number): string | null {
  const start = formatIcsUtc(auction.closing);
  if (!start) return null;
  const uid = `${auction.id || auction.auction_number}-${index}@mstc-auction-listings`;
  const summary = escapeIcsText(auctionSummary(auction));
  const location = escapeIcsText(
    auction.display_location_city ??
      auction.location ??
      auction.state ??
      auction.region ??
      "",
  );
  const descriptionParts = [
    auction.seller ? `Seller: ${auction.seller}` : null,
    auction.price_summary ? `Price: ${auction.price_summary}` : null,
    auction.emd_summary ? `EMD: ${auction.emd_summary}` : null,
    auction.detail_url ? `Details: ${auction.detail_url}` : null,
  ].filter(Boolean);
  const description = escapeIcsText(descriptionParts.join("\n"));
  const url = auction.detail_url ? `URL:${auction.detail_url}` : null;
  return [
    "BEGIN:VEVENT",
    `UID:${uid}`,
    `DTSTAMP:${formatIcsUtc(new Date().toISOString())}`,
    `DTSTART:${start}`,
    `SUMMARY:${summary}`,
    location ? `LOCATION:${location}` : null,
    description ? `DESCRIPTION:${description}` : null,
    url,
    "END:VEVENT",
  ]
    .filter(Boolean)
    .join("\r\n");
}
function buildCalendar(events: string[]): string {
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//MSTC Auction Listings//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    ...events,
    "END:VCALENDAR",
  ].join("\r\n");
}
function downloadIcs(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
export function auctionToIcsEvent(
  auction: AuctionRecord,
  index = 0,
): string | null {
  return buildEvent(auction, index);
}
export function auctionsToIcs(auctions: AuctionRecord[]): string {
  const events = auctions
    .map((auction, index) => buildEvent(auction, index))
    .filter((event): event is string => Boolean(event));
  return buildCalendar(events);
}
export function downloadIcsForAuction(auction: AuctionRecord): boolean {
  const event = buildEvent(auction, 0);
  if (!event) return false;
  const safeId = (auction.id || auction.auction_number).replace(
    /[^\w.-]+/g,
    "_",
  );
  downloadIcs(`auction-${safeId}-closing.ics`, buildCalendar([event]));
  return true;
}
export function downloadIcsForWatchlist(
  auctions: AuctionRecord[],
  ids: Iterable<string>,
): number {
  const idSet = ids instanceof Set ? ids : new Set(ids);
  const selected = auctions.filter((auction) => idSet.has(auction.id));
  const content = auctionsToIcs(selected);
  if (!content.includes("BEGIN:VEVENT")) return 0;
  const stamp = new Date().toISOString().slice(0, 10);
  downloadIcs(`watchlist-closings-${stamp}.ics`, content);
  return selected.length;
}
