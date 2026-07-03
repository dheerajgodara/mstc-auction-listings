import { parseClosingMs } from "@/lib/auction-filters";
import { getValuationFields, hasKnownValuation } from "@/lib/valuation";
import type { AuctionRecord } from "@/types/auction";

const DAY_MS = 24 * 60 * 60 * 1000;

function hasDocsOrPhotos(auction: AuctionRecord): boolean {
  return auction.lots.some(
    (lot) =>
      (lot.documents?.length ?? 0) > 0 || (lot.preview_images?.length ?? 0) > 0,
  );
}

function hasKnownPrice(auction: AuctionRecord): boolean {
  return (
    auction.price_parse_status === "numeric" ||
    auction.price_parse_status === "range" ||
    auction.min_start_price != null
  );
}

function hasKnownEmd(auction: AuctionRecord): boolean {
  return (
    auction.emd_parse_status === "auction_wise" ||
    auction.emd_parse_status === "item_wise" ||
    auction.pre_bid_emd_amount != null
  );
}

/** Higher = better opportunity signal (valuation unavailable uses quality-only signals). */
export function opportunityScore(auction: AuctionRecord, nowMs = Date.now()): number {
  let score = 0;
  const v = getValuationFields(auction);

  if (hasKnownValuation(auction) && v.valuation_status === "under_market") {
    score += 120;
  }

  if (auction.parse_confidence === "high") score += 40;
  else if (auction.parse_confidence === "medium") score += 20;

  if (hasDocsOrPhotos(auction)) score += 25;
  if (hasKnownPrice(auction)) score += 20;
  if (hasKnownEmd(auction)) score += 15;
  if (auction.location || auction.state) score += 10;

  const warnings = auction.warnings?.length ?? 0;
  const missing = auction.missing_fields?.length ?? 0;
  score -= warnings * 8;
  score -= missing * 3;

  const closingMs = parseClosingMs(auction.closing);
  if (closingMs != null && closingMs >= nowMs) {
    const days = (closingMs - nowMs) / DAY_MS;
    if (days <= 3) score += 30;
    else if (days <= 7) score += 20;
    else if (days <= 14) score += 10;
  }

  return score;
}

export function sortByOpportunity(
  auctions: AuctionRecord[],
  nowMs = Date.now(),
): AuctionRecord[] {
  return [...auctions].sort((a, b) => {
    const diff = opportunityScore(b, nowMs) - opportunityScore(a, nowMs);
    if (diff !== 0) return diff;
    return (parseClosingMs(a.closing) ?? 0) - (parseClosingMs(b.closing) ?? 0);
  });
}
