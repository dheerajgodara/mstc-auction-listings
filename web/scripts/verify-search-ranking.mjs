#!/usr/bin/env node
/**
 * Search ranking self-tests (mirrors web/src/lib/search.ts).
 */
const SEARCH_TIER = {
  EXACT_ID: 1000,
  SOURCE_ID: 900,
  TITLE: 800,
  LOT_TITLE: 700,
  SELLER_LOCATION: 600,
  CATEGORY_SOURCE: 500,
  DOCUMENT: 400,
  DESCRIPTION: 100,
};

function norm(value) {
  return (value ?? "").toLowerCase();
}

function scoreAuctionSearch(auction, rawQuery) {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return 0;

  const id = norm(auction.id);
  const sourceId = norm(auction.source_auction_id ?? auction.auction_number);
  if (id === query || sourceId === query) return SEARCH_TIER.EXACT_ID;
  if (id.includes(query) || sourceId.includes(query)) return SEARCH_TIER.SOURCE_ID;

  const title = norm(auction.item_summary);
  if (title.includes(query)) return SEARCH_TIER.TITLE;

  for (const lot of auction.lots ?? []) {
    const lotHay = norm(
      `${lot.item_title} ${lot.item_description ?? ""} ${lot.location ?? ""}`,
    );
    if (lotHay.includes(query)) return SEARCH_TIER.LOT_TITLE;
  }

  const sellerLoc = norm(
    `${auction.seller} ${auction.location} ${auction.state} ${auction.region}`,
  );
  if (sellerLoc.includes(query)) return SEARCH_TIER.SELLER_LOCATION;

  const sourceCat = norm(
    `${auction.source} ${auction.asset_category} ${auction.platform}`,
  );
  if (sourceCat.includes(query)) return SEARCH_TIER.CATEGORY_SOURCE;

  for (const lot of auction.lots ?? []) {
    for (const doc of lot.documents ?? []) {
      if (norm(doc.filename).includes(query)) return SEARCH_TIER.DOCUMENT;
    }
  }

  if (norm(auction.search_text).includes(query)) return SEARCH_TIER.DESCRIPTION;
  return null;
}

function rankAuctionsBySearch(auctions, query) {
  const q = query.trim();
  if (!q) return auctions;
  const scored = [];
  for (const auction of auctions) {
    const score = scoreAuctionSearch(auction, q);
    if (score !== null) scored.push({ auction, score });
  }
  scored.sort((a, b) => b.score - a.score || a.auction.id.localeCompare(b.auction.id));
  return scored.map((s) => s.auction);
}

const sample = [
  {
    id: "mstc-12345",
    source_auction_id: "AUC-999",
    item_summary: "Scrap steel auction",
    seller: "MSTC JPR",
    location: "Jaipur",
    state: "Rajasthan",
    source: "mstc",
    asset_category: "scrap",
    search_text: "long boilerplate description about steel melting",
    lots: [
      {
        item_title: "Lot 1 copper wire",
        item_description: "mixed copper",
        documents: [{ filename: "annexure-a.pdf" }],
      },
    ],
  },
  {
    id: "mstc-67890",
    source_auction_id: "AUC-100",
    item_summary: "Vehicle disposal",
    seller: "Delhi office",
    location: "Delhi",
    state: "Delhi",
    source: "mstc",
    asset_category: "vehicle",
    search_text: "cars and bikes",
    lots: [],
  },
];

function runTests() {
  const errors = [];
  const assert = (name, condition) => {
    if (!condition) errors.push(name);
  };

  assert("exact id", scoreAuctionSearch(sample[0], "mstc-12345") === SEARCH_TIER.EXACT_ID);
  assert("source id partial", scoreAuctionSearch(sample[0], "AUC-999") === SEARCH_TIER.EXACT_ID);
  assert("title match", scoreAuctionSearch(sample[0], "scrap steel") === SEARCH_TIER.TITLE);
  assert("lot title", scoreAuctionSearch(sample[0], "copper wire") === SEARCH_TIER.LOT_TITLE);
  assert("seller", scoreAuctionSearch(sample[0], "jpr") === SEARCH_TIER.SELLER_LOCATION);
  assert("document name", scoreAuctionSearch(sample[0], "annexure") === SEARCH_TIER.DOCUMENT);
  assert("description last", scoreAuctionSearch(sample[0], "boilerplate") === SEARCH_TIER.DESCRIPTION);
  assert("no match", scoreAuctionSearch(sample[0], "zzznomatch") === null);

  const ranked = rankAuctionsBySearch(sample, "AUC-999");
  assert("rank exact first", ranked[0]?.id === "mstc-12345");

  const titleRank = rankAuctionsBySearch(sample, "vehicle");
  assert("rank title beats description", titleRank[0]?.id === "mstc-67890");

  return errors;
}

const errors = runTests();
if (errors.length) {
  console.error("FAIL search-ranking:", errors.join(", "));
  process.exit(1);
}
console.log("OK  search-ranking self-tests");
