#!/usr/bin/env node
/** Pre-build: emit public/data/auction-routes.json from auctions.json + archive-auctions.json */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const auctionsPath = path.join(webRoot, "public", "data", "auctions.json");
const archivePath = path.join(webRoot, "public", "data", "archive-auctions.json");
const outPath = path.join(webRoot, "public", "data", "auction-routes.json");

if (!fs.existsSync(auctionsPath)) {
  console.error("generate-auction-routes: missing auctions.json");
  process.exit(1);
}
if (fs.statSync(auctionsPath).size === 0) {
  console.error(
    "generate-auction-routes: web/public/data/auctions.json is zero bytes — restore from web/out or promote a valid export",
  );
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(auctionsPath, "utf8"));
let archiveData = { auctions: [], generated_at: data.generated_at, automation_ran_at: data.automation_ran_at };
if (fs.existsSync(archivePath) && fs.statSync(archivePath).size > 0) {
  archiveData = JSON.parse(fs.readFileSync(archivePath, "utf8"));
}

const GRACE_DAYS = 30;
const MS_PER_DAY = 86400000;

function sourceSlug(source) {
  if (source === "gem_forward") return "gem-forward";
  if (source === "eauction") return "eauction";
  return "mstc";
}

function deriveRouteId(auction) {
  const source = auction.source ?? "mstc";
  let raw =
    auction.source_auction_id?.trim() ||
    auction.auction_number?.trim() ||
    auction.id?.trim() ||
    "";
  const prefix = `${source}:`;
  if (auction.id?.startsWith(prefix)) raw = auction.id.slice(prefix.length);
  else if (raw.includes(":")) raw = raw.slice(raw.indexOf(":") + 1);
  raw = raw.trim() || String(auction.id).replace(/^[^:]+:/, "");
  if (!/^[a-zA-Z0-9._-]+$/.test(raw)) {
    raw = raw.split("").map((ch) => (/^[a-zA-Z0-9._-]$/.test(ch) ? ch : encodeURIComponent(ch))).join("");
  }
  return raw;
}

function isIndexable(auction) {
  if (!auction.closing) return true;
  const t = Date.parse(auction.closing);
  return Number.isNaN(t) ? true : Date.now() <= t + GRACE_DAYS * MS_PER_DAY;
}

const used = new Set();
const routes = [];
const liveIds = new Set();

function addAuction(auction, { stampInto } = {}) {
  const source_slug = sourceSlug(auction.source);
  let route_id = deriveRouteId(auction);
  let key = `${source_slug}/${route_id}`;
  if (used.has(key)) {
    route_id = `${route_id}-${String(auction.id).replace(/[^a-zA-Z0-9]/g, "").slice(-6)}`;
    key = `${source_slug}/${route_id}`;
  }
  if (used.has(key)) return;
  used.add(key);
  auction.route_id = route_id;
  auction.source_slug = source_slug;
  if (stampInto) {
    // stamped on the object already
  }
  routes.push({
    id: auction.id,
    route_id,
    source_slug,
    lastmod: auction.imported_at || auction.first_seen_at || data.automation_ran_at,
    indexable: isIndexable(auction),
    title_hint: auction.display_title ?? auction.item_summary ?? null,
    in_archive: Boolean(auction.in_archive),
  });
}

for (const auction of data.auctions || []) {
  liveIds.add(String(auction.id));
  addAuction(auction, { stampInto: data });
}

let archiveStamped = 0;
for (const auction of archiveData.auctions || []) {
  if (liveIds.has(String(auction.id))) continue;
  addAuction(auction);
  archiveStamped += 1;
}

const exportData = {
  generated_at: data.generated_at,
  automation_ran_at: data.automation_ran_at,
  count: routes.length,
  live_count: (data.auctions || []).length,
  archive_count: archiveStamped,
  routes,
};

fs.writeFileSync(outPath, `${JSON.stringify(exportData, null, 2)}\n`, "utf8");
fs.writeFileSync(auctionsPath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
if (archiveData.auctions?.length) {
  fs.writeFileSync(archivePath, `${JSON.stringify(archiveData, null, 2)}\n`, "utf8");
}
console.log(
  `generate-auction-routes: wrote ${routes.length} routes (live=${(data.auctions || []).length} archive_extra=${archiveStamped})`,
);
