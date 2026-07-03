import type { AuctionRecord } from "@/types/auction";

export const SEARCH_TIER = {
  EXACT_ID: 1000,
  SOURCE_ID: 900,
  TITLE: 800,
  LOT_TITLE: 700,
  SELLER_LOCATION: 600,
  CATEGORY_SOURCE: 500,
  DOCUMENT: 400,
  DESCRIPTION: 100,
} as const;

function norm(value: string | null | undefined): string {
  return (value ?? "").toLowerCase();
}

function includes(hay: string, needle: string): boolean {
  return hay.includes(needle);
}

/** Higher score = better match. Null = no match. */
export function scoreAuctionSearch(
  auction: AuctionRecord,
  rawQuery: string,
): number | null {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return 0;

  const id = norm(auction.id);
  const sourceId = norm(auction.source_auction_id ?? auction.auction_number);
  if (id === query || sourceId === query) return SEARCH_TIER.EXACT_ID;
  if (id.includes(query) || sourceId.includes(query)) return SEARCH_TIER.SOURCE_ID;

  const title = norm(auction.item_summary);
  if (title.includes(query)) return SEARCH_TIER.TITLE;

  for (const lot of auction.lots) {
    const lotHay = norm(
      `${lot.item_title} ${lot.item_description ?? ""} ${lot.location ?? ""}`,
    );
    if (includes(lotHay, query)) return SEARCH_TIER.LOT_TITLE;
  }

  const sellerLoc = norm(
    `${auction.seller} ${auction.location} ${auction.state} ${auction.region}`,
  );
  if (includes(sellerLoc, query)) return SEARCH_TIER.SELLER_LOCATION;

  const sourceCat = norm(
    `${auction.source} ${auction.asset_category} ${auction.platform}`,
  );
  if (includes(sourceCat, query)) return SEARCH_TIER.CATEGORY_SOURCE;

  for (const lot of auction.lots) {
    for (const doc of lot.documents ?? []) {
      if (includes(norm(doc.filename), query)) return SEARCH_TIER.DOCUMENT;
    }
  }

  const blob = norm(auction.search_text);
  if (includes(blob, query)) return SEARCH_TIER.DESCRIPTION;

  return null;
}

export function matchesAuctionSearch(auction: AuctionRecord, query: string): boolean {
  return scoreAuctionSearch(auction, query) !== null;
}

export function rankAuctionsBySearch(
  auctions: AuctionRecord[],
  query: string,
): AuctionRecord[] {
  const q = query.trim();
  if (!q) return auctions;
  const scored: { auction: AuctionRecord; score: number }[] = [];
  for (const auction of auctions) {
    const score = scoreAuctionSearch(auction, q);
    if (score !== null) scored.push({ auction, score });
  }
  scored.sort((a, b) => b.score - a.score || a.auction.id.localeCompare(b.auction.id));
  return scored.map((s) => s.auction);
}
