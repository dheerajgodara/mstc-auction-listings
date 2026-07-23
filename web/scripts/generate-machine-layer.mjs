#!/usr/bin/env node
/**
 * Post-build: emit sanitized machine layer under out/api and out/feeds.
 * Only indexable auctions (aligned with SEO detail / sitemap policy).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");

const SITE_ROOT = (process.env.NEXT_PUBLIC_SITE_URL || "https://scrapauctionindia.com").replace(
  /\/$/,
  "",
);
const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH || "/auctions").replace(/\/$/, "");

const SOURCE_TO_SLUG = {
  mstc: "mstc",
  gem_forward: "gem-forward",
  eauction: "eauction",
};

const PORTAL_NAME = {
  mstc: "MSTC",
  gem_forward: "GeM Forward",
  eauction: "eAuction.gov.in",
};

const MATERIAL_SLUGS = [
  { slug: "ferrous", match: ["ferrous_scrap", "steel", "hms", "turning", "boring"] },
  { slug: "non-ferrous", match: ["aluminium", "copper", "brass", "conductor"] },
  { slug: "ewaste", match: ["ewaste", "e-waste", "pcb"] },
  { slug: "machinery", match: ["machinery", "plant", "loom", "equipment"] },
  { slug: "vehicle", match: ["vehicle"] },
  { slug: "coal", match: ["coal"] },
  { slug: "timber", match: ["timber", "wood"] },
  { slug: "scrap", match: ["scrap"] },
];

const LATEST_CAP = 200;

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function siteUrl(relativePath) {
  const rel = relativePath.startsWith("/") ? relativePath : `/${relativePath}`;
  return `${SITE_ROOT}${BASE_PATH}${rel}`;
}

function escapeXml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function csvEscape(v) {
  const s = v == null ? "" : String(v);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function isCdnMediaUrl(url) {
  if (!url || typeof url !== "string") return false;
  return (
    url.startsWith("https://files.csmg.in/") ||
    url.startsWith("https://files.scrapauctionindia.com/") ||
    /https:\/\/pub-[a-f0-9]+\.r2\.dev\//.test(url) ||
    /^https:\/\/[^/]+\/(?:pdfs|docs|thumbs)\//.test(url)
  );
}

function localAssetExists(relPath) {
  if (!relPath || typeof relPath !== "string") return false;
  if (isCdnMediaUrl(relPath)) return true;
  const cleaned = relPath.trim().replace(/^\//, "");
  if (!/^(pdfs|docs|thumbs)\//.test(cleaned)) return false;
  return fs.existsSync(path.join(outDir, cleaned));
}

function onlyIfLocal(relPath) {
  if (isCdnMediaUrl(relPath)) return relPath;
  return localAssetExists(relPath) ? relPath.replace(/^\//, "") : null;
}

function sourceSlug(source) {
  return SOURCE_TO_SLUG[source] ?? "mstc";
}

function portalName(source) {
  return PORTAL_NAME[source] ?? "official auction portal";
}

function parseClosingMs(closing) {
  if (!closing) return null;
  const t = Date.parse(closing);
  return Number.isFinite(t) ? t : null;
}

function istYmd(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function closingIstYmd(closing) {
  const ms = parseClosingMs(closing);
  if (ms == null) return null;
  return istYmd(new Date(ms));
}

function sanitizeLot(lot) {
  const documents = [];
  for (const doc of lot.documents ?? []) {
    const cached = onlyIfLocal(doc.cached_url);
    const thumb = onlyIfLocal(doc.thumbnail_url);
    if (!cached && !thumb) continue;
    documents.push({
      type: doc.type ?? "unknown",
      filename: doc.filename ?? null,
      status: doc.status ?? null,
      mime_type: doc.mime_type ?? null,
      page_count: doc.page_count ?? null,
      ...(cached ? { cached_url: cached } : {}),
      ...(thumb ? { thumbnail_url: thumb } : {}),
    });
  }
  const preview_images = (lot.preview_images ?? [])
    .map((img) => (typeof img === "string" ? onlyIfLocal(img) : null))
    .filter(Boolean);

  return {
    lot_id: lot.lot_id ?? null,
    item_title: lot.item_title ?? null,
    item_description: lot.item_description ?? null,
    quantity: lot.quantity ?? null,
    unit: lot.unit ?? null,
    location: lot.location ?? null,
    lot_state: lot.lot_state ?? null,
    category: lot.category ?? null,
    product_type: lot.product_type ?? null,
    start_price_inr: lot.start_price_inr ?? lot.start_price ?? null,
    start_price_label: lot.start_price_label ?? lot.start_price_text ?? null,
    gst: lot.gst ?? null,
    tcs: lot.tcs ?? null,
    tax_text: lot.tax_text ?? null,
    ai_heading: lot.ai_heading ?? null,
    ai_summary: lot.ai_summary ?? null,
    ai_tags: lot.ai_tags ?? [],
    document_count: documents.length,
    documents,
    preview_images,
  };
}

function countDocs(auction, lots) {
  let documents = 0;
  let photos = 0;
  if (auction.pdf_url && localAssetExists(auction.pdf_url)) documents += 1;
  for (const lot of lots) {
    documents += lot.documents?.length ?? 0;
    photos += (lot.documents ?? []).filter((d) => d.type === "photo").length;
    photos += lot.preview_images?.length ?? 0;
  }
  return { documents, photos };
}

function sanitizeAuction(auction, route) {
  const source = auction.source ?? "mstc";
  const slug = route.source_slug || sourceSlug(source);
  const routeId = route.route_id;
  const lots = (auction.lots ?? []).map(sanitizeLot);
  const pdf_url = onlyIfLocal(auction.pdf_url);
  const document_counts = countDocs({ pdf_url }, lots);
  const title =
    auction.display_title || auction.item_summary || auction.auction_number || null;
  const listingOnly = lots.length === 0;
  const needsDeep = listingOnly || !title;

  return {
    id: auction.id,
    source,
    route_id: routeId,
    canonical_url: siteUrl(`/${slug}/${routeId}/`),
    auction_number: auction.auction_number ?? null,
    title,
    item_summary: auction.item_summary ?? null,
    display_title: auction.display_title ?? null,
    display_buyer_summary: auction.display_buyer_summary ?? null,
    location: auction.location ?? null,
    display_location_city: auction.display_location_city ?? null,
    display_location_state: auction.display_location_state ?? null,
    display_location_raw: auction.display_location_raw ?? null,
    state: auction.state ?? auction.display_location_state ?? null,
    region: auction.region ?? null,
    seller: auction.seller ?? null,
    opening: auction.opening ?? null,
    closing: auction.closing ?? null,
    emd_summary: auction.emd_summary ?? null,
    emd_parse_status: auction.emd_parse_status ?? null,
    price_summary: auction.price_summary ?? null,
    tax_summary: auction.tax_summary ?? null,
    quantity_summary: auction.display_quantity_summary ?? null,
    display_total_quantity_mt: auction.display_total_quantity_mt ?? null,
    display_material_category: auction.display_material_category ?? null,
    material_tags: auction.ai_material_tags ?? [],
    lot_count: lots.length,
    total_lots: auction.total_lots ?? lots.length,
    lots_available: lots.length > 0,
    enrichment_status: listingOnly ? "listing_only" : "enriched",
    needs_deep_scrape: needsDeep,
    min_start_price: auction.min_start_price ?? null,
    max_start_price: auction.max_start_price ?? null,
    imported_at: auction.imported_at ?? null,
    first_seen_at: auction.first_seen_at ?? null,
    listed_at: auction.listed_at ?? null,
    official_portal_name: portalName(source),
    document_counts,
    ...(pdf_url ? { pdf_url } : {}),
    lots,
  };
}

function searchTextFrom(full) {
  return [
    full.title,
    full.item_summary,
    full.display_buyer_summary,
    full.quantity_summary,
    full.location,
    full.display_location_city,
    full.display_location_state,
    full.display_material_category,
    ...(full.material_tags ?? []),
    ...(full.lots ?? []).flatMap((l) => [l.item_title, l.item_description, l.quantity]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function slimRecord(full) {
  return {
    id: full.id,
    source: full.source,
    route_id: full.route_id,
    canonical_url: full.canonical_url,
    title: full.title,
    closing: full.closing,
    opening: full.opening,
    location: [full.display_location_city, full.display_location_state]
      .filter(Boolean)
      .join(", ") || full.location,
    state: full.state,
    emd_summary: full.emd_summary,
    price_summary: full.price_summary,
    quantity_summary: full.quantity_summary,
    display_total_quantity_mt: full.display_total_quantity_mt,
    lot_count: full.lot_count,
    lots_available: full.lots_available,
    enrichment_status: full.enrichment_status,
    needs_deep_scrape: full.needs_deep_scrape,
    material_category: full.display_material_category,
    official_portal_name: full.official_portal_name,
  };
}

function matchesMaterial(full, match) {
  const hay = [
    full.display_material_category,
    full.title,
    full.item_summary,
    ...(full.material_tags ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return match.some((m) => hay.includes(m.toLowerCase()));
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function writeCsv(filePath, rows, columns) {
  const lines = [columns.join(",")];
  for (const row of rows) {
    lines.push(columns.map((c) => csvEscape(row[c])).join(","));
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`, "utf8");
}

const SCHEMA = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  title: "ScrapAuctionIndiaPublicAuction",
  description:
    "Sanitized public auction record for agents. Discovery only — bid on official portals.",
  type: "object",
  properties: {
    id: { type: "string", description: "Internal auction id" },
    source: {
      type: "string",
      enum: ["mstc", "gem_forward", "eauction"],
      description: "Source system",
    },
    route_id: { type: "string", description: "Stable URL segment under /auctions/{source}/" },
    canonical_url: { type: "string", description: "Absolute HTML detail URL" },
    title: { type: "string" },
    item_summary: { type: ["string", "null"] },
    closing: { type: ["string", "null"], description: "ISO timestamp when available (often +05:30)" },
    opening: { type: ["string", "null"] },
    emd_summary: { type: ["string", "null"], description: "Earnest money deposit summary text" },
    price_summary: { type: ["string", "null"], description: "Floor/start price summary — not winning bid" },
    tax_summary: { type: ["string", "null"], description: "GST/TCS notes when available" },
    quantity_summary: { type: ["string", "null"] },
    display_total_quantity_mt: { type: ["number", "null"] },
    official_portal_name: {
      type: "string",
      description: "Where to bid officially (text only; no deep bid link)",
    },
    document_counts: {
      type: "object",
      properties: {
        documents: { type: "number" },
        photos: { type: "number" },
      },
    },
    pdf_url: {
      type: "string",
      description: "Relative path under /auctions/ when local PDF exists",
    },
    lots: {
      type: "array",
      description: "Public lot fields; local asset URLs only when files exist",
      items: { type: "object" },
    },
  },
};

const auctionsPath = path.join(outDir, "data", "auctions.json");
const routesPath = path.join(outDir, "data", "auction-routes.json");
if (!fs.existsSync(auctionsPath) || !fs.existsSync(routesPath)) {
  console.error("generate-machine-layer: missing auctions.json or auction-routes.json");
  process.exit(1);
}

const exportData = readJson(auctionsPath);
const routesData = readJson(routesPath);
const auctionById = new Map((exportData.auctions ?? []).map((a) => [a.id, a]));

const indexableRoutes = (routesData.routes ?? []).filter((r) => r.indexable !== false);
const sanitized = [];
const missingAuction = [];

for (const route of indexableRoutes) {
  const auction = auctionById.get(route.id);
  if (!auction) {
    missingAuction.push(route.id);
    continue;
  }
  sanitized.push(sanitizeAuction(auction, route));
}

const now = Date.now();
const generatedAt = new Date().toISOString();
const bySource = { mstc: 0, gem_forward: 0, eauction: 0 };
for (const a of sanitized) {
  if (a.source in bySource) bySource[a.source] += 1;
}

const sortedNewest = [...sanitized].sort((a, b) => {
  const ta = parseClosingMs(a.imported_at || a.first_seen_at || a.listed_at) ?? 0;
  const tb = parseClosingMs(b.imported_at || b.first_seen_at || b.listed_at) ?? 0;
  if (tb !== ta) return tb - ta;
  return String(b.route_id).localeCompare(String(a.route_id));
});

const latest = sortedNewest.slice(0, LATEST_CAP).map(slimRecord);
const closingSoon = sanitized
  .filter((a) => {
    const ms = parseClosingMs(a.closing);
    if (ms == null) return false;
    const delta = ms - now;
    return delta >= 0 && delta <= 72 * 60 * 60 * 1000;
  })
  .sort((a, b) => (parseClosingMs(a.closing) ?? 0) - (parseClosingMs(b.closing) ?? 0))
  .map(slimRecord);

const todayIst = istYmd();
const closingToday = sanitized
  .filter((a) => closingIstYmd(a.closing) === todayIst)
  .map(slimRecord);

const largeLots = sanitized
  .filter((a) => (a.display_total_quantity_mt ?? 0) >= 50 || (a.lot_count ?? 0) >= 20)
  .sort(
    (a, b) =>
      (b.display_total_quantity_mt ?? 0) - (a.display_total_quantity_mt ?? 0),
  )
  .map(slimRecord);

// Wipe prior machine auction files for a clean rebuild
const auctionApiRoot = path.join(outDir, "api", "auction");
if (fs.existsSync(auctionApiRoot)) {
  fs.rmSync(auctionApiRoot, { recursive: true, force: true });
}
const materialsRoot = path.join(outDir, "feeds", "materials");
if (fs.existsSync(materialsRoot)) {
  fs.rmSync(materialsRoot, { recursive: true, force: true });
}

for (const full of sanitized) {
  const slug = sourceSlug(full.source);
  writeJson(path.join(outDir, "api", "auction", slug, `${full.route_id}.json`), full);
}

for (const src of ["mstc", "gem_forward", "eauction"]) {
  const slug = sourceSlug(src);
  const list = sanitized.filter((a) => a.source === src).map(slimRecord);
  writeJson(path.join(outDir, "api", "source", `${slug}.json`), {
    generated_at: generatedAt,
    source: src,
    source_slug: slug,
    count: list.length,
    auctions: list,
  });
}

writeJson(path.join(outDir, "api", "schema.json"), SCHEMA);
writeJson(path.join(outDir, "api", "latest.json"), {
  generated_at: generatedAt,
  count: latest.length,
  auctions: latest,
});
writeJson(path.join(outDir, "api", "closing-soon.json"), {
  generated_at: generatedAt,
  window_hours: 72,
  count: closingSoon.length,
  auctions: closingSoon,
});

const SEARCH_TOPICS = [
  {
    slug: "aluminium",
    match: ["aluminium", "aluminum", "conductor"],
  },
  { slug: "copper", match: ["copper", "cable", "brass"] },
  { slug: "vehicle-scrap", match: ["vehicle"] },
];

const searchRoot = path.join(outDir, "api", "search");
if (fs.existsSync(searchRoot)) {
  fs.rmSync(searchRoot, { recursive: true, force: true });
}

const searchIndex = sanitized.map((full) => ({
  ...slimRecord(full),
  search_text: searchTextFrom(full),
  material_tags: full.material_tags ?? [],
}));

writeJson(path.join(outDir, "api", "search-index.json"), {
  generated_at: generatedAt,
  count: searchIndex.length,
  note: "Download and filter locally. There is no /api/search.json?q= endpoint on static hosting.",
  auctions: searchIndex,
});

for (const topic of SEARCH_TOPICS) {
  const list = sanitized
    .filter((a) => matchesMaterial(a, topic.match))
    .map(slimRecord);
  writeJson(path.join(outDir, "api", "search", `${topic.slug}.json`), {
    generated_at: generatedAt,
    topic: topic.slug,
    count: list.length,
    auctions: list,
  });
}

writeJson(path.join(outDir, "api", "search", "large-lots.json"), {
  generated_at: generatedAt,
  topic: "large-lots",
  count: largeLots.length,
  auctions: largeLots,
});
writeJson(path.join(outDir, "api", "search", "closing-soon.json"), {
  generated_at: generatedAt,
  topic: "closing-soon",
  window_hours: 72,
  count: closingSoon.length,
  auctions: closingSoon,
});

const shallowCount = sanitized.filter((a) => a.needs_deep_scrape).length;

const endpoints = [
  "/api/manifest.json",
  "/api/schema.json",
  "/api/latest.json",
  "/api/closing-soon.json",
  "/api/search-index.json",
  "/api/search/aluminium.json",
  "/api/search/copper.json",
  "/api/search/vehicle-scrap.json",
  "/api/search/large-lots.json",
  "/api/search/closing-soon.json",
  "/api/archive/latest.json",
  "/api/archive/search-index.json",
  "/api/source/mstc.json",
  "/api/source/gem-forward.json",
  "/api/source/eauction.json",
  "/feeds/latest.json",
  "/feeds/latest.csv",
  "/feeds/large-lots.json",
  "/feeds/large-lots.csv",
  "/feeds/closing-today.json",
  "/llms.txt",
  "/llms-full.txt",
  "/machine-sitemap.xml",
  "/developers/",
  "/closing-soon/",
  "/archive/",
  "/large-scrap-lots/",
];

// --- T-30 archive machine layer ---
const archivePath = path.join(outDir, "data", "archive-auctions.json");
const publicArchivePath = path.join(webRoot, "public", "data", "archive-auctions.json");
let archiveExport = { auctions: [], generated_at: generatedAt, count: 0 };
const archiveSrc = fs.existsSync(archivePath)
  ? archivePath
  : fs.existsSync(publicArchivePath)
    ? publicArchivePath
    : null;
if (archiveSrc) {
  archiveExport = readJson(archiveSrc);
}
const routeByAuctionId = new Map((routesData.routes || []).map((r) => [r.id, r]));
const archiveSanitized = [];
for (const auction of archiveExport.auctions || []) {
  const route =
    routeByAuctionId.get(auction.id) || {
      id: auction.id,
      route_id: String(auction.source_auction_id || auction.id).replace(/[^a-zA-Z0-9._-]/g, ""),
      source_slug: sourceSlug(auction.source),
    };
  const full = sanitizeAuction(auction, route);
  full.archive_reason = auction.archive_reason ?? null;
  full.catalogue_status = auction.catalogue_status ?? null;
  full.in_archive = true;
  archiveSanitized.push(full);
  writeJson(
    path.join(outDir, "api", "archive", "auction", sourceSlug(full.source), `${full.route_id}.json`),
    full,
  );
}
const archiveSearchIndex = archiveSanitized.map((full) => ({
  ...slimRecord(full),
  search_text: searchTextFrom(full),
  archive_reason: full.archive_reason ?? null,
  catalogue_status: full.catalogue_status ?? null,
  material_tags: full.material_tags ?? [],
}));
writeJson(path.join(outDir, "api", "archive", "latest.json"), {
  generated_at: generatedAt,
  retention_days: 30,
  count: archiveSanitized.length,
  auctions: archiveSanitized.map(slimRecord),
});
writeJson(path.join(outDir, "api", "archive", "search-index.json"), {
  generated_at: generatedAt,
  retention_days: 30,
  count: archiveSearchIndex.length,
  auctions: archiveSearchIndex,
});

writeJson(path.join(outDir, "api", "manifest.json"), {
  generated_at: generatedAt,
  automation_ran_at: exportData.automation_ran_at ?? null,
  site: siteUrl("/"),
  counts: {
    indexable_auctions: sanitized.length,
    archive_auctions: archiveSanitized.length,
    by_source: bySource,
    latest_cap: LATEST_CAP,
    closing_soon: closingSoon.length,
    closing_today: closingToday.length,
    large_lots: largeLots.length,
    needs_deep_scrape: shallowCount,
  },
  endpoints: endpoints.map((e) => siteUrl(e)),
  notes: [
    "HTML SEO sitemap is /sitemap.xml (pages only).",
    "Machine discovery: this manifest, /llms.txt, /api/search-index.json, /api/search/{topic}.json.",
    "T-30 archive (short-window + recently closed): /archive/, /api/archive/latest.json, /api/archive/search-index.json.",
    "Filter search-index locally — there is no dynamic /api/search.json?q= on static hosting.",
    "/data/ is blocked in robots.txt and is not a crawler API.",
    "listing_only / needs_deep_scrape flag shallow per-auction JSON (empty lots).",
  ],
});

writeJson(path.join(outDir, "feeds", "latest.json"), {
  generated_at: generatedAt,
  count: latest.length,
  auctions: latest,
});
writeCsv(
  path.join(outDir, "feeds", "latest.csv"),
  latest,
  [
    "id",
    "source",
    "route_id",
    "canonical_url",
    "title",
    "closing",
    "state",
    "emd_summary",
    "price_summary",
    "quantity_summary",
    "lot_count",
    "official_portal_name",
  ],
);

writeJson(path.join(outDir, "feeds", "large-lots.json"), {
  generated_at: generatedAt,
  count: largeLots.length,
  auctions: largeLots,
});
writeCsv(
  path.join(outDir, "feeds", "large-lots.csv"),
  largeLots,
  [
    "id",
    "source",
    "route_id",
    "canonical_url",
    "title",
    "closing",
    "display_total_quantity_mt",
    "lot_count",
    "quantity_summary",
    "official_portal_name",
  ],
);

writeJson(path.join(outDir, "feeds", "closing-today.json"), {
  generated_at: generatedAt,
  timezone: "Asia/Kolkata",
  date: todayIst,
  count: closingToday.length,
  auctions: closingToday,
});

for (const mat of MATERIAL_SLUGS) {
  const list = sanitized.filter((a) => matchesMaterial(a, mat.match)).map(slimRecord);
  writeJson(path.join(outDir, "feeds", "materials", `${mat.slug}.json`), {
    generated_at: generatedAt,
    material: mat.slug,
    count: list.length,
    auctions: list,
  });
}

const machineLocs = new Set([
  siteUrl("/llms.txt"),
  siteUrl("/llms-full.txt"),
  siteUrl("/api/manifest.json"),
  siteUrl("/api/schema.json"),
  siteUrl("/api/latest.json"),
  siteUrl("/api/closing-soon.json"),
  siteUrl("/api/search-index.json"),
  siteUrl("/api/archive/latest.json"),
  siteUrl("/api/archive/search-index.json"),
  siteUrl("/api/search/aluminium.json"),
  siteUrl("/api/search/copper.json"),
  siteUrl("/api/search/vehicle-scrap.json"),
  siteUrl("/api/search/large-lots.json"),
  siteUrl("/api/search/closing-soon.json"),
  siteUrl("/api/source/mstc.json"),
  siteUrl("/api/source/gem-forward.json"),
  siteUrl("/api/source/eauction.json"),
  siteUrl("/feeds/latest.json"),
  siteUrl("/feeds/latest.csv"),
  siteUrl("/feeds/large-lots.json"),
  siteUrl("/feeds/large-lots.csv"),
  siteUrl("/feeds/closing-today.json"),
  siteUrl("/machine-sitemap.xml"),
  siteUrl("/archive/"),
]);
for (const mat of MATERIAL_SLUGS) {
  machineLocs.add(siteUrl(`/feeds/materials/${mat.slug}.json`));
}
for (const full of sanitized) {
  machineLocs.add(siteUrl(`/api/auction/${sourceSlug(full.source)}/${full.route_id}.json`));
}
for (const full of archiveSanitized) {
  machineLocs.add(
    siteUrl(`/api/archive/auction/${sourceSlug(full.source)}/${full.route_id}.json`),
  );
}

const machineBody = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${[...machineLocs]
  .sort()
  .map(
    (loc) => `  <url>
    <loc>${escapeXml(loc)}</loc>
    <lastmod>${generatedAt.slice(0, 10)}</lastmod>
  </url>`,
  )
  .join("\n")}
</urlset>
`;
fs.writeFileSync(path.join(outDir, "machine-sitemap.xml"), machineBody, "utf8");

if (missingAuction.length) {
  console.warn(
    `generate-machine-layer: ${missingAuction.length} indexable routes missing from auctions.json (skipped)`,
  );
}

console.log(
  `generate-machine-layer: ${sanitized.length} indexable + ${archiveSanitized.length} archive → api/ + feeds/ + machine-sitemap.xml`,
);
