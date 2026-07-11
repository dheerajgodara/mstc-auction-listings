import type { AiConfidence, AuctionRecord, LotRecord } from "@/types/auction";

export type DisplayMaterialCategory =
  | "transmission_scrap"
  | "aluminium_conductor"
  | "ferrous_scrap"
  | "cable_scrap"
  | "transformer_oil"
  | "vehicle_lot"
  | "timber"
  | "machinery"
  | "coal"
  | "minerals"
  | "property"
  | "other";

export type DisplayLocationConfidence = "high" | "medium" | "low";

export const DISPLAY_MATERIAL_CATEGORIES: {
  id: DisplayMaterialCategory | "All";
  label: string;
}[] = [
  { id: "All", label: "All materials" },
  { id: "transmission_scrap", label: "Transmission scrap" },
  { id: "aluminium_conductor", label: "Aluminium conductor" },
  { id: "ferrous_scrap", label: "Ferrous scrap" },
  { id: "cable_scrap", label: "Cable scrap" },
  { id: "transformer_oil", label: "Transformer oil" },
  { id: "vehicle_lot", label: "Vehicle lot" },
  { id: "timber", label: "Timber" },
  { id: "machinery", label: "Machinery" },
  { id: "coal", label: "Coal" },
  { id: "minerals", label: "Minerals" },
  { id: "property", label: "Property" },
  { id: "other", label: "Other" },
];

export const MATERIAL_CATEGORY_LABELS: Record<DisplayMaterialCategory, string> =
  {
    transmission_scrap: "Transmission scrap",
    aluminium_conductor: "Aluminium conductor",
    ferrous_scrap: "Ferrous scrap",
    cable_scrap: "Cable scrap",
    transformer_oil: "Transformer oil",
    vehicle_lot: "Vehicle lot",
    timber: "Timber",
    machinery: "Machinery",
    coal: "Coal",
    minerals: "Minerals",
    property: "Property",
    other: "Other",
  };

const CITY_ALIASES: Record<string, { city: string; state?: string }> = {
  ballia: { city: "Ballia", state: "Uttar Pradesh" },
  azamgarh: { city: "Azamgarh", state: "Uttar Pradesh" },
  kanpur: { city: "Kanpur", state: "Uttar Pradesh" },
  panki: { city: "Kanpur", state: "Uttar Pradesh" },
  mumbai: { city: "Mumbai", state: "Maharashtra" },
  panvel: { city: "Panvel", state: "Maharashtra" },
  "navi mumbai": { city: "Navi Mumbai", state: "Maharashtra" },
  bangalore: { city: "Bengaluru", state: "Karnataka" },
  bengaluru: { city: "Bengaluru", state: "Karnataka" },
  rajajinagar: { city: "Bengaluru", state: "Karnataka" },
  bhandara: { city: "Bhandara", state: "Maharashtra" },
  gadegaon: { city: "Gadegaon", state: "Maharashtra" },
  kolkata: { city: "Kolkata", state: "West Bengal" },
  "new town": { city: "Kolkata", state: "West Bengal" },
  howrah: { city: "Howrah", state: "West Bengal" },
};

const INDIAN_STATES = new Set([
  "andhra pradesh",
  "arunachal pradesh",
  "assam",
  "bihar",
  "chhattisgarh",
  "goa",
  "gujarat",
  "haryana",
  "himachal pradesh",
  "jharkhand",
  "karnataka",
  "kerala",
  "madhya pradesh",
  "maharashtra",
  "manipur",
  "meghalaya",
  "mizoram",
  "nagaland",
  "odisha",
  "punjab",
  "rajasthan",
  "sikkim",
  "tamil nadu",
  "telangana",
  "tripura",
  "uttar pradesh",
  "uttarakhand",
  "west bengal",
  "delhi",
  "jammu and kashmir",
  "ladakh",
  "puducherry",
  "chandigarh",
]);

function cleanText(value?: string | null): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function titleCaseCity(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => (p ? p[0].toUpperCase() + p.slice(1).toLowerCase() : ""))
    .join(" ");
}

function parseQuantityMt(
  quantity?: string | null,
  unit?: string | null,
): number | null {
  if (!quantity) return null;
  const q = quantity.replace(/,/g, "").trim();
  const embedded = /^([\d.]+)\s*(MT|MTS|TON|TONS|KG|KGS|LOT|LOTS)\b/i.exec(q);
  let value: number;
  let u: string;
  if (embedded) {
    value = Number.parseFloat(embedded[1]);
    u = embedded[2].toUpperCase();
  } else {
    const m = /([\d,]+(?:\.\d+)?)/.exec(q);
    if (!m) return null;
    value = Number.parseFloat(m[1].replace(/,/g, ""));
    u = (unit ?? "").trim().toUpperCase();
  }
  if (Number.isNaN(value)) return null;
  if (u === "KG" || u === "KGS") return value / 1000;
  if (u === "MT" || u === "MTS" || u === "TON" || u === "TONS") return value;
  return null;
}

function lotQuantityMt(lot: LotRecord): number | null {
  const direct = parseQuantityMt(lot.quantity, lot.unit);
  if (direct != null) return direct;
  const blob = [
    lot.item_title,
    lot.item_description,
    lot.lot_description_text,
    lot.lot_details_text,
  ]
    .filter(Boolean)
    .join(" ");
  const re = /(\d[\d,]*(?:\.\d+)?)\s*(MT|MTS|TON|TONS|KG|KGS)\b/gi;
  let total = 0;
  let found = false;
  for (const match of blob.matchAll(re)) {
    const val = Number.parseFloat(match[1].replace(/,/g, ""));
    const unit = match[2].toUpperCase();
    if (unit.startsWith("KG")) total += val / 1000;
    else total += val;
    found = true;
  }
  return found ? total : null;
}

export function formatMt(value: number): string {
  if (value >= 100)
    return value.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  if (value >= 10)
    return value.toLocaleString("en-IN", { maximumFractionDigits: 1 });
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function classifyMaterial(
  blob: string,
  assetCategory?: string | null,
): { key: DisplayMaterialCategory; label: string } {
  const patterns: [RegExp, DisplayMaterialCategory][] = [
    [
      /tower|transmission|earth\s*wire|acsr|conductor|moose|panther|deer/i,
      "transmission_scrap",
    ],
    [/alumin|aluminium|aluminum/i, "aluminium_conductor"],
    [/cable/i, "cable_scrap"],
    [/transformer\s*oil|insulating\s*oil/i, "transformer_oil"],
    [/vehicle|car|bus|truck|auto/i, "vehicle_lot"],
    [/timber|wood|teak|\bsal\b/i, "timber"],
    [/machinery|machine|plant|equipment/i, "machinery"],
    [/\bcoal\b/i, "coal"],
    [/mineral|ore|bauxite|iron\s*ore/i, "minerals"],
    [/property|land|building|flat/i, "property"],
    [/ms\s*scrap|ferrous|iron\s*scrap|steel\s*scrap|hms/i, "ferrous_scrap"],
    [/scrap/i, "ferrous_scrap"],
  ];
  for (const [re, key] of patterns) {
    if (re.test(blob)) return { key, label: MATERIAL_CATEGORY_LABELS[key] };
  }
  if (assetCategory === "timber") return { key: "timber", label: "Timber" };
  if (assetCategory === "vehicle")
    return { key: "vehicle_lot", label: "Vehicle lot" };
  if (assetCategory === "machinery")
    return { key: "machinery", label: "Machinery" };
  if (assetCategory === "coal") return { key: "coal", label: "Coal" };
  if (assetCategory === "minerals")
    return { key: "minerals", label: "Minerals" };
  if (assetCategory === "property")
    return { key: "property", label: "Property" };
  return { key: "other", label: "Other" };
}

function shortMaterialLabel(
  category: DisplayMaterialCategory,
  blob: string,
): string {
  if (category === "transmission_scrap") {
    if (/tower/i.test(blob) && /conductor|acsr|earth/i.test(blob)) {
      return "Transmission Tower & Conductor Scrap";
    }
    if (/conductor|acsr|moose|panther|deer/i.test(blob))
      return "Conductor Scrap";
    return "Transmission Scrap";
  }
  if (category === "aluminium_conductor") {
    return /cable/i.test(blob) ? "Aluminium Cable Scrap" : "Aluminium Scrap";
  }
  if (category === "ferrous_scrap") return "Ferrous Scrap";
  if (category === "cable_scrap") return "Cable Scrap";
  if (category === "transformer_oil") return "Transformer Oil";
  if (category === "vehicle_lot") return "Vehicle Lot";
  if (category === "timber") return "Timber Lot";
  if (category === "machinery") return "Machinery Lot";
  if (category === "coal") return "Coal Lot";
  if (category === "minerals") return "Minerals Lot";
  if (category === "property") return "Property Lot";
  return "Scrap Lot";
}

export function normalizeLocation(
  raw?: string | null,
  state?: string | null,
  lots: LotRecord[] = [],
  opts?: { officeAddress?: string | null; seller?: string | null },
): {
  city: string | null;
  state: string | null;
  raw: string | null;
  confidence: DisplayLocationConfidence;
} {
  const rawClean = cleanText(raw) || cleanText(lots[0]?.location);
  let stateClean = cleanText(state) || cleanText(lots[0]?.lot_state);
  if (stateClean) stateClean = titleCaseCity(stateClean);

  const lower = rawClean.toLowerCase();
  const searchBlob = [lower, opts?.officeAddress, opts?.seller]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  let city: string | null = null;
  let inferredState: string | null = stateClean;

  for (const [token, info] of Object.entries(CITY_ALIASES)) {
    if (searchBlob.includes(token)) {
      city = info.city;
      inferredState = inferredState ?? info.state ?? null;
      break;
    }
  }

  if (!city && rawClean) {
    const parts = rawClean
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
    for (const part of parts) {
      const pl = part.toLowerCase();
      if (INDIAN_STATES.has(pl)) {
        inferredState = titleCaseCity(part);
        continue;
      }
      if (/^\d{6}$/.test(part)) continue;
      if (
        part.length >= 3 &&
        !/\b(kv|sub.?station|depot|yard|site)\b/i.test(pl)
      ) {
        city = titleCaseCity(part);
        break;
      }
    }
  }

  if (!city && stateClean && rawClean && rawClean.length <= 40) {
    city = titleCaseCity(rawClean);
  }

  if (city && inferredState)
    return {
      city,
      state: inferredState,
      raw: rawClean || null,
      confidence: "high",
    };
  if (city)
    return {
      city,
      state: inferredState,
      raw: rawClean || null,
      confidence: "medium",
    };
  if (inferredState && rawClean)
    return {
      city: null,
      state: inferredState,
      raw: rawClean,
      confidence: "low",
    };
  if (rawClean)
    return { city: null, state: null, raw: rawClean, confidence: "low" };
  return { city: null, state: null, raw: null, confidence: "low" };
}

function buildQuantitySummary(lots: LotRecord[]): {
  summary: string | null;
  totalMt: number | null;
} {
  if (!lots.length) return { summary: null, totalMt: null };
  const lotParts: { label: string; mt: number }[] = [];
  let totalMt = 0;
  let hasMt = false;

  for (const lot of lots) {
    const mt = lotQuantityMt(lot);
    const label = cleanText(lot.item_title) || `Lot ${lot.lot_id}`;
    if (mt != null && mt > 0) {
      lotParts.push({ label, mt });
      totalMt += mt;
      hasMt = true;
    }
  }

  if (hasMt && lotParts.length) {
    if (lotParts.length === 1) {
      const { label, mt } = lotParts[0];
      return { summary: `${formatMt(mt)} MT ${label}`, totalMt };
    }
    if (lotParts.length <= 3) {
      const detail = lotParts
        .map(({ label, mt }) => `${formatMt(mt)} MT ${label}`)
        .join(" · ");
      return { summary: `${lots.length} lots · ${detail}`, totalMt };
    }
    const top = [...lotParts].sort((a, b) => b.mt - a.mt).slice(0, 3);
    const detail = top
      .map(({ label, mt }) => `${formatMt(mt)} MT ${label}`)
      .join(" · ");
    return {
      summary: `${lots.length} lots · ${formatMt(totalMt)} MT total · ${detail}`,
      totalMt,
    };
  }

  if (lots.length > 1) return { summary: `${lots.length} lots`, totalMt: null };
  return { summary: null, totalMt: null };
}

function truncateTitle(text: string, maxLen: number): string {
  const cleaned = cleanText(text);
  if (cleaned.length <= maxLen) return cleaned;
  const cut = cleaned.slice(0, maxLen - 1).replace(/\s+\S*$/, "");
  return `${cut}…`;
}

function buildDisplayTitle(
  auction: AuctionRecord,
  lots: LotRecord[],
  materialCategory: DisplayMaterialCategory,
  totalMt: number | null,
): string {
  const blob = [
    auction.item_summary,
    ...lots.map((l) => l.item_title),
    ...lots.map((l) => l.item_description ?? ""),
  ]
    .filter(Boolean)
    .join(" ");
  const shortMaterial = shortMaterialLabel(materialCategory, blob);

  if (totalMt && totalMt > 0) return `${formatMt(totalMt)} MT ${shortMaterial}`;

  if (lots.length === 1) {
    const title = cleanText(lots[0].item_title);
    if (title && title.length <= 80) return title;
    if (title) return truncateTitle(title, 80);
  }

  const summary = cleanText(auction.item_summary);
  if (
    summary &&
    summary.length <= 90 &&
    !summary.toLowerCase().startsWith("bids are invited")
  ) {
    return summary;
  }
  if (summary && materialCategory !== "other") return shortMaterial;
  if (summary) return truncateTitle(summary, 90);
  return shortMaterial;
}

function buildBuyerSummary(
  auction: AuctionRecord,
  qtySummary: string | null,
  matLabel: string,
  locationLine: string | null,
): string | null {
  const bits: string[] = [];
  if (auction.price_summary) bits.push(auction.price_summary);
  else if (auction.min_start_price != null && auction.min_start_price > 0) {
    bits.push(
      `Floor ₹${Math.round(auction.min_start_price).toLocaleString("en-IN")}`,
    );
  }
  if (auction.emd_summary)
    bits.push(auction.emd_summary.split(";")[0].trim().slice(0, 60));
  if (qtySummary) bits.push(qtySummary);
  else if (matLabel) bits.push(matLabel);
  if (locationLine) bits.push(locationLine);
  return bits.length ? bits.join(" · ") : null;
}

export function enrichAuctionDisplay(auction: AuctionRecord): AuctionRecord {
  if (auction.display_title) return auction;

  const lots = auction.lots ?? [];
  const loc = normalizeLocation(auction.location, auction.state, lots, {
    officeAddress: auction.office_address,
    seller: auction.seller,
  });
  const blob = [
    auction.item_summary,
    auction.location,
    ...lots.map((l) => l.item_title),
    ...lots.map((l) => l.item_description ?? ""),
  ]
    .filter(Boolean)
    .join(" ");
  const { key: matKey } = classifyMaterial(blob, auction.asset_category);
  const { summary: qtySummary, totalMt } = buildQuantitySummary(lots);
  const displayTitle = buildDisplayTitle(auction, lots, matKey, totalMt);
  const keyLots = lots
    .map((l) => cleanText(l.item_title))
    .filter((t, i, arr) => t && arr.indexOf(t) === i)
    .slice(0, 4);

  const locationLine =
    loc.city && loc.state
      ? `${loc.city}, ${loc.state}`
      : (loc.city ?? loc.state ?? null);
  const matLabel = MATERIAL_CATEGORY_LABELS[matKey];
  const buyerSummary = buildBuyerSummary(
    auction,
    qtySummary,
    matLabel,
    locationLine,
  );

  return {
    ...auction,
    display_title: displayTitle,
    display_location_city: loc.city,
    display_location_state: loc.state,
    display_location_raw: loc.raw ?? cleanText(auction.location) ?? null,
    display_quantity_summary: qtySummary,
    display_material_category: matKey,
    display_key_lots: keyLots,
    display_buyer_summary: buyerSummary,
    display_location_confidence: loc.confidence,
    display_total_quantity_mt: totalMt,
  };
}

export function enrichAuctions(auctions: AuctionRecord[]): AuctionRecord[] {
  return auctions.map(enrichAuctionDisplay);
}

export function displaySearchText(auction: AuctionRecord): string {
  const enriched = enrichAuctionDisplay(auction);
  return [
    enriched.display_title,
    enriched.display_buyer_summary,
    enriched.display_location_city,
    enriched.display_location_state,
    enriched.display_location_raw,
    enriched.display_quantity_summary,
    enriched.display_material_category,
    ...(enriched.display_key_lots ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function auctionTotalMt(auction: AuctionRecord): number | null {
  const enriched = enrichAuctionDisplay(auction);
  if (enriched.display_total_quantity_mt != null)
    return enriched.display_total_quantity_mt;
  let total = 0;
  let found = false;
  for (const lot of auction.lots ?? []) {
    const mt = lotQuantityMt(lot);
    if (mt != null) {
      total += mt;
      found = true;
    }
  }
  return found ? total : null;
}

export function materialCategoryLabel(
  category?: DisplayMaterialCategory | string | null,
): string | null {
  if (!category) return null;
  return MATERIAL_CATEGORY_LABELS[category as DisplayMaterialCategory] ?? null;
}

const AI_TAG_LABELS: Record<string, string> = {
  transmission_scrap: "Transmission scrap",
  aluminium_conductor: "Aluminium",
  ferrous_scrap: "Ferrous scrap",
  cable_scrap: "Cable scrap",
  transformer_oil: "Transformer oil",
  vehicle_lot: "Vehicle",
  timber: "Timber",
  coal: "Coal",
  minerals: "Minerals",
  machinery: "Machinery",
  property: "Property",
  ewaste: "E-waste",
  other_scrap: "Scrap",
  large_lot: "Large lot",
  multi_lot: "Multi-lot",
  documents_available: "Documents",
  photos_available: "Photos",
  site_inspection: "Inspection",
  closing_soon: "Closing soon",
  low_location_confidence: "Location uncertain",
  missing_document: "Missing docs",
  source_window_limited: "Limited window",
  price_undisclosed: "Price undisclosed",
};

export function isAiReady(auction: AuctionRecord): boolean {
  return auction.ai_status === "ready" && Boolean(auction.ai_clean_heading);
}

export function isAiConfidenceUsable(confidence?: AiConfidence | null): boolean {
  return confidence === "high" || confidence === "medium";
}

export function resolveDisplayTitle(auction: AuctionRecord): string {
  if (
    isAiReady(auction) &&
    isAiConfidenceUsable(auction.ai_confidence) &&
    auction.ai_clean_heading
  ) {
    return auction.ai_clean_heading;
  }
  return enrichAuctionDisplay(auction).display_title ?? auction.item_summary ?? "—";
}

export function resolveDisplayBuyerSummary(
  auction: AuctionRecord,
): string | null {
  if (
    isAiReady(auction) &&
    isAiConfidenceUsable(auction.ai_confidence) &&
    auction.ai_buyer_summary
  ) {
    return auction.ai_buyer_summary;
  }
  return enrichAuctionDisplay(auction).display_buyer_summary ?? null;
}

export function resolveAiTags(auction: AuctionRecord): string[] {
  if (!isAiReady(auction)) return [];
  const tags = [
    ...(auction.ai_material_tags ?? []),
    ...(auction.ai_buyer_intent_tags ?? []),
  ];
  return tags.filter((tag, index) => tags.indexOf(tag) === index);
}

export function aiTagLabel(tag: string): string {
  return AI_TAG_LABELS[tag] ?? tag.replace(/_/g, " ");
}

export function aiSearchText(auction: AuctionRecord): string {
  if (!isAiReady(auction)) return "";
  const parts = [
    auction.ai_clean_heading,
    auction.ai_buyer_summary,
    auction.ai_clean_location_label,
    ...(auction.ai_material_tags ?? []),
    ...(auction.ai_buyer_intent_tags ?? []),
    ...(auction.ai_risk_notes ?? []),
  ];
  for (const lot of auction.lots ?? []) {
    if (lot.ai_status === "ready") {
      parts.push(lot.ai_heading, lot.ai_summary, ...(lot.ai_tags ?? []));
    }
  }
  return parts.filter(Boolean).join(" ").toLowerCase();
}
