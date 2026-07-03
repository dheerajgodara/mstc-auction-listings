import type { AuctionRecord } from "@/types/auction";

export const SEARCH_TIER = {
  EXACT_ID: 1000,
  ID_STARTS: 900,
  AUCTION_NUMBER: 850,
  ID_CONTAINS: 800,
  LOT_ID: 750,
  TITLE: 700,
  LOT_TITLE: 600,
  SELLER_LOCATION: 500,
  CATEGORY_SOURCE: 450,
  DOCUMENT: 400,
  URL: 350,
  DESCRIPTION: 100,
} as const;

const SOURCE_PREFIXES = ["mstc", "gem_forward", "gem", "eauction"] as const;

function norm(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

/** Collapse non-alphanumeric to nothing (for prefix/separator-insensitive matching). */
function alnum(value: string): string {
  return value.replace(/[^\p{L}\p{N}]+/gu, "");
}

/** Strip a leading source prefix like "mstc:", "gem_forward-", "eauction_", "gem forward " */
export function stripSourcePrefix(id: string): string {
  const m = /^(mstc|gem[_ -]?forward|gem|eauction)[\s:_\-]+(.+)$/i.exec(id);
  return m ? m[2] : id;
}

/** All ID-like variants of an auction, lower-cased. */
export function buildIdVariants(auction: AuctionRecord): string[] {
  const variants = new Set<string>();
  const add = (v: string | null | undefined) => {
    const s = norm(v);
    if (s) variants.add(s);
  };

  const rawId = norm(auction.id);
  const stripped = norm(stripSourcePrefix(rawId));
  const sourceId = norm(auction.source_auction_id);
  const auctionNo = norm(auction.auction_number);
  const source = norm(auction.source ?? "mstc");

  add(rawId);
  add(stripped);
  add(sourceId);
  add(auctionNo);

  // Bracketed ID inside MSTC auction numbers, e.g. `MSTC/.../14365[584985]`
  const bracket = auctionNo.match(/\[([^\]]+)\]/);
  if (bracket) add(bracket[1]);

  // Source-prefixed combos (mstc:584985, mstc_584985, mstc-584985, mstc 584985, mstc584985)
  const numericPart = sourceId || stripped;
  if (source && numericPart) {
    add(`${source}:${numericPart}`);
    add(`${source}_${numericPart}`);
    add(`${source}-${numericPart}`);
    add(`${source} ${numericPart}`);
    add(`${source}${numericPart}`);
  }
  return Array.from(variants);
}

function auctionNumberTokens(auctionNo: string): string[] {
  if (!auctionNo) return [];
  return auctionNo
    .split(/[^\p{L}\p{N}]+/gu)
    .map((t) => t.toLowerCase())
    .filter((t) => t.length > 0);
}

function collectUrls(auction: AuctionRecord): string[] {
  const urls: string[] = [];
  if (auction.detail_url) urls.push(auction.detail_url);
  if (auction.pdf_url) urls.push(auction.pdf_url);
  if (auction.source_pdf_url) urls.push(auction.source_pdf_url);
  if (auction.mstc_html_url) urls.push(auction.mstc_html_url);
  if (auction.document_urls) urls.push(...auction.document_urls);
  return urls;
}

/** Higher score = better match. Null = no match. Empty query returns 0. */
export function scoreAuctionSearch(
  auction: AuctionRecord,
  rawQuery: string,
): number | null {
  const query = norm(rawQuery);
  if (!query) return 0;
  const queryAlnum = alnum(query);

  const variants = buildIdVariants(auction);
  const auctionNo = norm(auction.auction_number);

  // Tier 1: exact ID match on any variant (separator-insensitive)
  for (const v of variants) {
    if (v === query) return SEARCH_TIER.EXACT_ID;
    if (queryAlnum && alnum(v) === queryAlnum) return SEARCH_TIER.EXACT_ID;
  }

  // Tier 2: any variant starts with query
  for (const v of variants) {
    if (v.startsWith(query)) return SEARCH_TIER.ID_STARTS;
    if (queryAlnum && alnum(v).startsWith(queryAlnum)) return SEARCH_TIER.ID_STARTS;
  }

  // Tier 3: auction_number full-string contains (MSTC composite numbers)
  if (auctionNo && auctionNo.includes(query)) return SEARCH_TIER.AUCTION_NUMBER;
  if (auctionNo && queryAlnum && alnum(auctionNo).includes(queryAlnum)) {
    return SEARCH_TIER.AUCTION_NUMBER;
  }

  // Tier 4: any variant contains query
  for (const v of variants) {
    if (v.includes(query)) return SEARCH_TIER.ID_CONTAINS;
    if (queryAlnum && alnum(v).includes(queryAlnum)) return SEARCH_TIER.ID_CONTAINS;
  }

  // Tier 5: lot_id exact match
  for (const lot of auction.lots ?? []) {
    const lotId = norm(lot.lot_id);
    if (lotId && (lotId === query || alnum(lotId) === queryAlnum)) {
      return SEARCH_TIER.LOT_ID;
    }
  }

  // Tier 6: title/item summary
  const title = norm(auction.item_summary);
  if (title.includes(query)) return SEARCH_TIER.TITLE;

  // Tier 7: lot title/description/location/lot_id substring
  for (const lot of auction.lots ?? []) {
    const lotHay = norm(
      `${lot.item_title} ${lot.item_description ?? ""} ${lot.location ?? ""} ${lot.lot_id ?? ""}`,
    );
    if (lotHay.includes(query)) return SEARCH_TIER.LOT_TITLE;
  }

  // Tier 8: seller / location / state / region / office / address
  const sellerLoc = norm(
    `${auction.seller ?? ""} ${auction.location ?? ""} ${auction.state ?? ""} ${auction.region ?? ""} ${auction.office ?? ""} ${auction.office_address ?? ""}`,
  );
  if (sellerLoc.includes(query)) return SEARCH_TIER.SELLER_LOCATION;

  // Tier 9: source / category / platform
  const sourceCat = norm(
    `${auction.source ?? ""} ${auction.asset_category ?? ""} ${auction.platform ?? ""}`,
  );
  if (sourceCat.includes(query)) return SEARCH_TIER.CATEGORY_SOURCE;

  // Tier 10: document filenames
  for (const lot of auction.lots ?? []) {
    for (const doc of lot.documents ?? []) {
      if (norm(doc.filename).includes(query)) return SEARCH_TIER.DOCUMENT;
    }
  }

  // Tier 11: URL strings (detail/pdf/mstc/html/documents)
  const urlBlob = collectUrls(auction).map(norm).join(" ");
  if (urlBlob && urlBlob.includes(query)) return SEARCH_TIER.URL;
  if (urlBlob && queryAlnum && alnum(urlBlob).includes(queryAlnum)) {
    return SEARCH_TIER.URL;
  }

  // Tier 12: long description / auction_number tokens fallback
  if (norm(auction.search_text).includes(query)) return SEARCH_TIER.DESCRIPTION;
  const tokens = auctionNumberTokens(auctionNo);
  if (tokens.some((t) => t === query || t.startsWith(query))) {
    return SEARCH_TIER.DESCRIPTION;
  }

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
    if (score !== null && score > 0) scored.push({ auction, score });
  }
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.auction.id.localeCompare(b.auction.id);
  });
  return scored.map((s) => s.auction);
}
