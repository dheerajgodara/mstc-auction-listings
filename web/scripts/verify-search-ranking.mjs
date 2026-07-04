#!/usr/bin/env node
/**
 * Search ranking self-tests (mirrors web/src/lib/search.ts).
 * Includes regression cases for real auction IDs.
 */
const SEARCH_TIER = {
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
};

function norm(value) {
  return (value ?? "").toString().trim().toLowerCase();
}

function alnum(v) {
  return v.replace(/[^\p{L}\p{N}]+/gu, "");
}

function stripSourcePrefix(id) {
  const m = /^(mstc|gem[_ -]?forward|gem|eauction)[\s:_\-]+(.+)$/i.exec(id);
  return m ? m[2] : id;
}

function buildIdVariants(a) {
  const out = new Set();
  const add = (v) => {
    const s = norm(v);
    if (s) out.add(s);
  };
  const rawId = norm(a.id);
  const stripped = norm(stripSourcePrefix(rawId));
  const sourceId = norm(a.source_auction_id);
  const auctionNo = norm(a.auction_number);
  const source = norm(a.source ?? "mstc");
  add(rawId);
  add(stripped);
  add(sourceId);
  add(auctionNo);
  const bracket = auctionNo.match(/\[([^\]]+)\]/);
  if (bracket) add(bracket[1]);
  const numericPart = sourceId || stripped;
  if (source && numericPart) {
    add(`${source}:${numericPart}`);
    add(`${source}_${numericPart}`);
    add(`${source}-${numericPart}`);
    add(`${source} ${numericPart}`);
    add(`${source}${numericPart}`);
  }
  return Array.from(out);
}

function collectUrls(a) {
  const urls = [];
  if (a.detail_url) urls.push(a.detail_url);
  if (a.pdf_url) urls.push(a.pdf_url);
  if (a.source_pdf_url) urls.push(a.source_pdf_url);
  if (a.mstc_html_url) urls.push(a.mstc_html_url);
  if (a.document_urls) urls.push(...a.document_urls);
  return urls;
}

function auctionNumberTokens(s) {
  if (!s) return [];
  return s.split(/[^\p{L}\p{N}]+/gu).map((t) => t.toLowerCase()).filter(Boolean);
}

function scoreAuctionSearch(a, rawQuery) {
  const query = norm(rawQuery);
  if (!query) return 0;
  const queryAlnum = alnum(query);
  const variants = buildIdVariants(a);
  const auctionNo = norm(a.auction_number);

  for (const v of variants) {
    if (v === query) return SEARCH_TIER.EXACT_ID;
    if (queryAlnum && alnum(v) === queryAlnum) return SEARCH_TIER.EXACT_ID;
  }
  for (const v of variants) {
    if (v.startsWith(query)) return SEARCH_TIER.ID_STARTS;
    if (queryAlnum && alnum(v).startsWith(queryAlnum)) return SEARCH_TIER.ID_STARTS;
  }
  if (auctionNo && auctionNo.includes(query)) return SEARCH_TIER.AUCTION_NUMBER;
  if (auctionNo && queryAlnum && alnum(auctionNo).includes(queryAlnum)) {
    return SEARCH_TIER.AUCTION_NUMBER;
  }
  for (const v of variants) {
    if (v.includes(query)) return SEARCH_TIER.ID_CONTAINS;
    if (queryAlnum && alnum(v).includes(queryAlnum)) return SEARCH_TIER.ID_CONTAINS;
  }
  for (const lot of a.lots ?? []) {
    const lotId = norm(lot.lot_id);
    if (lotId && (lotId === query || alnum(lotId) === queryAlnum)) {
      return SEARCH_TIER.LOT_ID;
    }
  }
  const displayTitle = norm(a.display_title);
  if (displayTitle.includes(query)) return SEARCH_TIER.TITLE;
  const title = norm(a.item_summary);
  if (title.includes(query)) return SEARCH_TIER.TITLE;
  for (const lot of a.lots ?? []) {
    const lotHay = norm(
      `${lot.item_title} ${lot.item_description ?? ""} ${lot.location ?? ""} ${lot.lot_id ?? ""}`,
    );
    if (lotHay.includes(query)) return SEARCH_TIER.LOT_TITLE;
  }
  const sellerLoc = norm(
    `${a.seller ?? ""} ${a.location ?? ""} ${a.state ?? ""} ${a.region ?? ""} ${a.office ?? ""} ${a.office_address ?? ""} ${a.display_location_city ?? ""} ${a.display_location_state ?? ""} ${a.display_location_raw ?? ""} ${a.display_buyer_summary ?? ""} ${a.display_material_category ?? ""}`,
  );
  if (sellerLoc.includes(query)) return SEARCH_TIER.SELLER_LOCATION;
  const sourceCat = norm(
    `${a.source ?? ""} ${a.asset_category ?? ""} ${a.platform ?? ""}`,
  );
  if (sourceCat.includes(query)) return SEARCH_TIER.CATEGORY_SOURCE;
  for (const lot of a.lots ?? []) {
    for (const doc of lot.documents ?? []) {
      if (norm(doc.filename).includes(query)) return SEARCH_TIER.DOCUMENT;
    }
  }
  const urlBlob = collectUrls(a).map(norm).join(" ");
  if (urlBlob && urlBlob.includes(query)) return SEARCH_TIER.URL;
  if (urlBlob && queryAlnum && alnum(urlBlob).includes(queryAlnum)) {
    return SEARCH_TIER.URL;
  }
  if (norm(a.search_text).includes(query)) return SEARCH_TIER.DESCRIPTION;
  const tokens = auctionNumberTokens(auctionNo);
  if (tokens.some((t) => t === query || t.startsWith(query))) {
    return SEARCH_TIER.DESCRIPTION;
  }
  return null;
}

function rankAuctionsBySearch(auctions, query) {
  const q = query.trim();
  if (!q) return auctions;
  const scored = [];
  for (const a of auctions) {
    const s = scoreAuctionSearch(a, q);
    if (s !== null && s > 0) scored.push({ a, s });
  }
  scored.sort((x, y) => y.s - x.s || (x.a.id ?? "").localeCompare(y.a.id ?? ""));
  return scored.map((v) => v.a);
}

// --------- Synthetic test cases ---------
const mstc1 = {
  id: "584985",
  source: "mstc",
  source_auction_id: "584985",
  auction_number:
    "MSTC/BLR/BANGALORE ELECTRICITY SUPPLY COMPANY LIMITED/4/Rajajinagar, Bangalore/26-27/14365[584985]",
  detail_url:
    "https://www.mstcindia.co.in/TenderEntry/Lot_Item_Details_AucID.aspx?ARID=584985",
  seller: "BESCOM",
  location: "Bangalore",
  state: "Karnataka",
  region: "BLR",
  item_summary: "Scrap disposal from Rajajinagar substation",
  lots: [{ lot_id: "1", item_title: "Aluminium scrap" }],
};
const mstcTower = {
  id: "582972",
  source: "mstc",
  source_auction_id: "582972",
  auction_number: "MSTC/LKO/582972",
  location: "CIVIL LINE BALLIA",
  state: "Uttar Pradesh",
  region: "LKO",
  display_title: "459 MT Transmission Tower & Conductor Scrap",
  display_location_city: "Ballia",
  display_location_state: "Uttar Pradesh",
  display_material_category: "transmission_scrap",
  item_summary: "Tower Parts; Earthwire 7/3.15mm; ACSR Dog CONDUCTOR",
  lots: [
    { lot_id: "1", item_title: "Tower Parts" },
    { lot_id: "2", item_title: "Earthwire 7/3.15mm" },
    { lot_id: "3", item_title: "ACSR Dog CONDUCTOR" },
  ],
};
const mstc2 = {
  id: "588051",
  source: "mstc",
  source_auction_id: "588051",
  auction_number: "MSTC/WRO/MAHATRANSCO/7/PANVEL/26-27/17337[588051]",
  seller: "MAHATRANSCO",
  location: "Panvel",
  state: "Maharashtra",
  region: "WRO",
  lots: [{ lot_id: "01" }],
};
const gem1 = {
  id: "gem_forward:36121",
  source: "gem_forward",
  source_auction_id: "36121",
  auction_number: "36121",
  detail_url:
    "https://forwardauction.gem.gov.in/eprocure/view-auction-notice/36121/0/17445C5",
  seller: "GeM Buyer",
  location: "Delhi",
  state: "Delhi",
  region: "N",
  lots: [{ lot_id: "1" }],
};
const eauction1 = {
  id: "eauction:2026_MH_34847",
  source: "eauction",
  source_auction_id: "2026_MH_34847",
  auction_number: "2026_MH_34847",
  detail_url: "https://eauction.gov.in/eAuction/app?component=view",
  seller: "MH Dept",
  location: "Mumbai",
  state: "Maharashtra",
  region: "West",
  lots: [{ lot_id: "1" }],
};
const distractor = {
  id: "999999",
  source: "mstc",
  source_auction_id: "999999",
  auction_number: "MSTC/HO/UNRELATED/99/CITY/26-27/99999[999999]",
  seller: "Someone",
  location: "Nowhere",
  state: "XY",
  region: "HO",
  search_text: "584985 also appears here as noise",
  lots: [],
};

const corpus = [distractor, gem1, eauction1, mstc2, mstcTower, mstc1];

function runTests() {
  const errors = [];
  const assert = (name, cond) => {
    if (!cond) errors.push(name);
  };

  // Exact ID rank #1 for real targets
  for (const target of ["584985", "588051"]) {
    const r = rankAuctionsBySearch(corpus, target);
    assert(
      `exact id ${target} ranks first (got ${r[0]?.id})`,
      r[0]?.id === target,
    );
  }

  // GeM numeric-only search still finds gem_forward
  const gemNum = rankAuctionsBySearch(corpus, "36121");
  assert(
    `gem numeric-only 36121 first (got ${gemNum[0]?.id})`,
    gemNum[0]?.id === "gem_forward:36121",
  );

  // GeM prefixed forms
  for (const q of ["gem_forward:36121", "gem_forward-36121", "gem_forward_36121", "gem forward 36121"]) {
    const r = rankAuctionsBySearch(corpus, q);
    assert(
      `gem prefixed query "${q}" ranks gem first (got ${r[0]?.id})`,
      r[0]?.id === "gem_forward:36121",
    );
  }

  // eAuction full source id
  const ea = rankAuctionsBySearch(corpus, "2026_MH_34847");
  assert(
    `eauction id first (got ${ea[0]?.id})`,
    ea[0]?.id === "eauction:2026_MH_34847",
  );

  // MSTC source-prefixed variants
  for (const q of ["mstc_584985", "mstc-584985", "mstc:584985", "MSTC 584985"]) {
    const r = rankAuctionsBySearch(corpus, q);
    assert(
      `mstc prefixed "${q}" ranks 584985 first (got ${r[0]?.id})`,
      r[0]?.id === "584985",
    );
  }

  // Partial numeric prefix still finds target and ranks above descriptor noise
  const partial = rankAuctionsBySearch(corpus, "5849");
  assert(
    `partial 5849 finds 584985 (got ${partial[0]?.id})`,
    partial[0]?.id === "584985",
  );

  // Auction number substring (internal MSTC ref before bracket)
  const internal = rankAuctionsBySearch(corpus, "14365");
  assert(
    `internal 14365 ranks 584985 first (got ${internal[0]?.id})`,
    internal[0]?.id === "584985",
  );

  // Bracketed ID matches even without brackets
  const bracket = rankAuctionsBySearch(corpus, "[584985]");
  assert(
    `bracketed [584985] finds 584985 (got ${bracket[0]?.id})`,
    bracket[0]?.id === "584985",
  );

  // Lot ID exact match wins over description noise
  const lot = rankAuctionsBySearch(corpus, "999999");
  assert(
    `id 999999 finds 999999 (got ${lot[0]?.id})`,
    lot[0]?.id === "999999",
  );

  // Case-insensitive
  const upper = rankAuctionsBySearch(corpus, "GEM_FORWARD:36121");
  assert(
    `uppercase gem prefix (got ${upper[0]?.id})`,
    upper[0]?.id === "gem_forward:36121",
  );

  // Text search still works
  const text = rankAuctionsBySearch(corpus, "bescom");
  assert(
    `seller text bescom (got ${text[0]?.id})`,
    text[0]?.id === "584985",
  );

  // Description noise loses to exact ID
  const noise = rankAuctionsBySearch(corpus, "584985");
  assert(
    `exact 584985 beats description noise from 999999`,
    noise[0]?.id === "584985" && noise.indexOf(distractor) > 0,
  );

  // Display enrichment search: city, material, tower
  const ballia = rankAuctionsBySearch(corpus, "Ballia");
  assert(
    `Ballia finds 582972 (got ${ballia[0]?.id})`,
    ballia[0]?.id === "582972",
  );
  const tower = rankAuctionsBySearch(corpus, "tower");
  assert(
    `tower finds 582972 in top (got ${tower[0]?.id})`,
    tower[0]?.id === "582972",
  );
  const acsr = rankAuctionsBySearch(corpus, "ACSR");
  assert(
    `ACSR finds 582972 (got ${acsr[0]?.id})`,
    acsr[0]?.id === "582972",
  );
  const moose = rankAuctionsBySearch(corpus, "588051");
  assert(
    `588051 id search (got ${moose[0]?.id})`,
    moose[0]?.id === "588051",
  );

  return errors;
}

const errors = runTests();
if (errors.length) {
  console.error("FAIL search-ranking:");
  for (const e of errors) console.error("  -", e);
  process.exit(1);
}
console.log("OK  search-ranking self-tests");
