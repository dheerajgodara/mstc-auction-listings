#!/usr/bin/env node
/** Shared SEO verification helpers for build scripts. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const webRoot = path.resolve(__dirname, "..");
export const outDir = path.join(webRoot, "out");

export const SITE_ROOT = (process.env.NEXT_PUBLIC_SITE_URL || "https://scrapauctionindia.com").replace(
  /\/$/,
  "",
);
export const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH || "/auctions").replace(/\/$/, "");

/** Substrings that must not appear in canonical URLs or sitemap locs. */
export const STAGING_DOMAIN_MARKERS = [
  "hostinger",
  "000webhost",
  "localhost",
  "127.0.0.1",
  "vercel.app",
  "netlify.app",
];

export const NOINDEX_UTILITY_PAGES = [
  "map",
  "watchlist",
  "saved",
  "status",
  "insights",
  "liquidate",
  "account",
  "support",
  "terms",
  "privacy",
  "refund-policy",
  "launch-readiness",
];

/** Business-facing indexable pages (not SEO material landings). */
export const INDEXABLE_COMMERCE_SLUGS = ["pricing"];

export const INDEXABLE_LANDING_SLUGS = [
  "mstc-auctions",
  "gem-forward-auctions",
  "eauction-gov-in",
  "scrap",
  "metal-scrap",
  "aluminium-scrap",
  "vehicle-auctions",
  "timber-auctions",
  "coal-auctions",
  "accessibility",
];

/** Preferred detail IDs for SEO/paywall regression — may age out of the export. */
export const PREFERRED_REGRESSION_DETAIL_PAGES = [
  { source: "mstc", id: "582972" },
  { source: "mstc", id: "584985" },
  { source: "mstc", id: "588051" },
];

/** @deprecated Prefer resolveRegressionDetailPages(); kept for callers that only need preferred IDs. */
export const REGRESSION_DETAIL_PAGES = PREFERRED_REGRESSION_DETAIL_PAGES;

const DETAIL_SOURCE_DIRS = ["mstc", "gem-forward", "eauction"];

/** List auction detail pages that exist under out/<source>/<id>/index.html. */
export function listBuiltDetailPages(limit = 100) {
  const pages = [];
  for (const source of DETAIL_SOURCE_DIRS) {
    const dir = path.join(outDir, source);
    if (!fs.existsSync(dir)) continue;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const id = entry.name;
      if (!fs.existsSync(path.join(dir, id, "index.html"))) continue;
      pages.push({ source, id });
      if (pages.length >= limit) return pages;
    }
  }
  return pages;
}

/**
 * Resolve regression detail pages from the current build.
 * Prefers PREFERRED_REGRESSION_DETAIL_PAGES when still exported; otherwise
 * falls back to any built detail pages so aged-out auction IDs cannot fail CI.
 */
export function resolveRegressionDetailPages(minCount = 2) {
  const preferred = PREFERRED_REGRESSION_DETAIL_PAGES.filter(({ source, id }) =>
    fs.existsSync(path.join(outDir, source, id, "index.html")),
  );
  if (preferred.length >= minCount) return preferred;

  const seen = new Set(preferred.map((p) => `${p.source}/${p.id}`));
  const fallback = listBuiltDetailPages(120).filter((p) => !seen.has(`${p.source}/${p.id}`));
  const merged = [...preferred, ...fallback];
  const target = Math.max(minCount, Math.min(PREFERRED_REGRESSION_DETAIL_PAGES.length, merged.length));
  return merged.slice(0, target);
}

/** Utility paths that must never appear in sitemap locs. */
export const FORBIDDEN_SITEMAP_UTILITY_PATHS = [
  "/map/",
  "/watchlist/",
  "/saved/",
  "/status/",
  "/insights/",
  "/liquidate/",
  "/account/",
  "/support/",
  "/terms/",
  "/privacy/",
  "/refund-policy/",
  "/launch-readiness/",
];

/** Raw asset paths that must never appear in sitemap locs. */
export const FORBIDDEN_SITEMAP_ASSET_PATHS = ["/data/", "/pdfs/", "/docs/", "/thumbs/"];

/** Hub pages are exported for navigation but intentionally noindex and omitted from sitemap. */
export const NOINDEX_HUB_PREFIX = "/hub/";

export const EXPECTED_ROBOTS_SITEMAP_URL = `${SITE_ROOT}${BASE_PATH}/sitemap.xml`;

/** Minimum visible text length on indexable landing pages (strip tags). */
export const MIN_LANDING_VISIBLE_TEXT = 120;

/** Unsafe wording that implies this site is an official government portal. */
export const OFFICIAL_CLAIM_PATTERNS = [
  /official scrap auction india/i,
  /official auction portal/i,
  /official government auction site/i,
  /official mstc\b/i,
  /official gem\b/i,
  /official eauction/i,
  /this is the official/i,
];

/** Schema types that must not appear on detail/landing pages. */
export const DISALLOWED_SCHEMA_TYPES = [
  "Review",
  "AggregateRating",
  "Rating",
  "Product",
];

export const OG_TWITTER_PROPERTIES = [
  "og:title",
  "og:description",
  "og:url",
  "twitter:card",
  "twitter:title",
];

export function readHtml(rel) {
  const normalized = rel.replace(/^\//, "").replace(/\/$/, "");
  const p = path.join(outDir, normalized, "index.html");
  return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : "";
}

export function readRootIndex() {
  const p = path.join(outDir, "index.html");
  return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : "";
}

export function extractMetaContent(html, nameOrProperty) {
  const re = new RegExp(
    `<meta[^>]+(?:name|property)=["']${nameOrProperty}["'][^>]+content=["']([^"']*)["']`,
    "i",
  );
  const m = html.match(re);
  if (m) return m[1];
  const re2 = new RegExp(
    `<meta[^>]+content=["']([^"']*)["'][^>]+(?:name|property)=["']${nameOrProperty}["']`,
    "i",
  );
  return re2.exec(html)?.[1] ?? "";
}

export function extractCanonical(html) {
  const m = html.match(/<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']/i);
  if (m) return m[1];
  const m2 = html.match(/<link[^>]+href=["']([^"']+)["'][^>]+rel=["']canonical["']/i);
  return m2?.[1] ?? "";
}

export function extractTitle(html) {
  const m = html.match(/<title[^>]*>([^<]*)<\/title>/i);
  return m?.[1]?.trim() ?? "";
}

export function extractH1(html) {
  const m = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  if (!m) return "";
  return m[1].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

export function visibleTextLength(html) {
  const body = html.match(/<body[^>]*>([\s\S]*)<\/body>/i)?.[1] ?? html;
  const text = body
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text.length;
}

export function hasInternalDetailLink(html) {
  return (
    /href=["'][^"']*\/(mstc|gem-forward|eauction)\/[^"'/?#]+/i.test(html) ||
    /href=["']https:\/\/scrapauctionindia\.com\/auctions\/(mstc|gem-forward|eauction)\//i.test(html)
  );
}

export function hasOfficialClaim(text) {
  return OFFICIAL_CLAIM_PATTERNS.some((re) => re.test(text));
}

export function extractJsonLdBlocks(html) {
  const blocks = [];
  const re = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    blocks.push(m[1].trim());
  }
  return blocks;
}

export function hasStagingLeak(text) {
  const lower = text.toLowerCase();
  return STAGING_DOMAIN_MARKERS.some((marker) => lower.includes(marker));
}

export function classifySitemapUrl(loc) {
  if (loc.endsWith(`${BASE_PATH}/`) || loc.endsWith(`${BASE_PATH}`)) return "home";
  const rel = loc.replace(SITE_ROOT, "").replace(BASE_PATH, "");
  if (/\/(mstc|gem-forward|eauction)\/[^/]+\/$/.test(rel)) return "detail";
  if (rel.includes("/state/")) return "state";
  if (/\/pricing\/$/.test(rel)) return "commerce";
  return "landing";
}

export function detailSourceFromSitemapUrl(loc) {
  const rel = loc.replace(SITE_ROOT, "").replace(BASE_PATH, "");
  const m = rel.match(/\/(mstc|gem-forward|eauction)\/[^/]+\/$/);
  return m?.[1] ?? null;
}

export function sitemapUrlViolations(loc) {
  const rel = loc.replace(SITE_ROOT, "").replace(BASE_PATH, "");
  const violations = [];
  for (const segment of FORBIDDEN_SITEMAP_UTILITY_PATHS) {
    if (rel.includes(segment)) violations.push({ type: "utility", segment });
  }
  for (const segment of FORBIDDEN_SITEMAP_ASSET_PATHS) {
    if (rel.includes(segment)) violations.push({ type: "asset", segment });
  }
  if (rel.includes(NOINDEX_HUB_PREFIX)) violations.push({ type: "hub", segment: NOINDEX_HUB_PREFIX });
  return violations;
}

export function collectSchemaTypes(parsed) {
  const types = new Set();
  function walk(node) {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item);
      return;
    }
    if (node["@type"]) {
      const t = node["@type"];
      if (Array.isArray(t)) t.forEach((x) => types.add(x));
      else types.add(t);
    }
    for (const v of Object.values(node)) walk(v);
  }
  walk(parsed);
  return [...types];
}

export function sitemapUrlsFromXml(xml) {
  const urls = [];
  const re = /<loc>([^<]+)<\/loc>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    urls.push(m[1].trim());
  }
  return urls;
}

export function htmlPathForSitemapUrl(loc) {
  const prefix = `${SITE_ROOT}${BASE_PATH}`;
  if (!loc.startsWith(prefix)) return null;
  let rel = loc.slice(prefix.length);
  if (rel === "/" || rel === "") return path.join(outDir, "index.html");
  rel = rel.replace(/^\//, "").replace(/\/$/, "");
  return path.join(outDir, rel, "index.html");
}
