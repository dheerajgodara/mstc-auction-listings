#!/usr/bin/env node
/**
 * Generate HTML-only sitemap index + child sitemaps (never /api/ or /feeds/).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { classifySitemapUrl } from "./seo-lib.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");

const SITE_ROOT = (process.env.NEXT_PUBLIC_SITE_URL || "https://scrapauctionindia.com").replace(
  /\/$/,
  "",
);
const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH || "/auctions").replace(/\/$/, "");

function siteUrl(relativePath) {
  const rel = relativePath.startsWith("/") ? relativePath : `/${relativePath}`;
  const normalized = rel.endsWith("/") ? rel : `${rel}/`;
  return `${SITE_ROOT}${BASE_PATH}${normalized === "/" ? "/" : normalized}`;
}

function escapeXml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function isMachineUrl(loc) {
  return (
    loc.includes("/api/") ||
    loc.includes("/feeds/") ||
    loc.includes("/machine-sitemap") ||
    loc.includes("/llms.txt") ||
    loc.includes("/llms-full.txt") ||
    loc.includes("/data/")
  );
}

function writeUrlset(fileName, urls, lastmod) {
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${[...urls]
  .sort()
  .map(
    (loc) => `  <url>
    <loc>${escapeXml(loc)}</loc>
    <lastmod>${lastmod}</lastmod>
  </url>`,
  )
  .join("\n")}
</urlset>
`;
  const outPath = path.join(outDir, fileName);
  fs.writeFileSync(outPath, body, "utf8");
  return outPath;
}

const routesPath = path.join(outDir, "data", "auction-routes.json");
if (!fs.existsSync(routesPath)) {
  console.error("generate-sitemap: missing auction-routes.json — run prepare-public-data first");
  process.exit(1);
}

const routesData = readJson(routesPath);
const lastmod = routesData.automation_ran_at?.slice(0, 10) ?? new Date().toISOString().slice(0, 10);

const auctionUrls = new Set();
for (const route of routesData.routes ?? []) {
  if (route.indexable === false) continue;
  auctionUrls.add(siteUrl(`/${route.source_slug}/${route.route_id}/`));
}

const sourceLandingUrls = new Set([siteUrl("/")]);
const sourceLandings = [
  "/mstc-auctions/",
  "/gem-forward-auctions/",
  "/eauction-gov-in/",
];
for (const lp of sourceLandings) {
  const htmlPath = path.join(outDir, lp.replace(/^\//, ""), "index.html");
  if (fs.existsSync(htmlPath) && !fs.readFileSync(htmlPath, "utf8").includes("noindex")) {
    sourceLandingUrls.add(siteUrl(lp));
  }
}

const stateUrls = new Set();
const stateConfigPath = path.join(webRoot, "public", "data", "seo-state-pages.json");
if (fs.existsSync(stateConfigPath)) {
  const states = readJson(stateConfigPath);
  for (const st of states) {
    const htmlPath = path.join(outDir, "state", st.slug, "index.html");
    if (fs.existsSync(htmlPath)) {
      stateUrls.add(siteUrl(`/state/${st.slug}/`));
    }
  }
}

const materialUrls = new Set();
const materialLandings = [
  "/scrap/",
  "/metal-scrap/",
  "/aluminium-scrap/",
  "/copper-scrap/",
  "/vehicle-auctions/",
  "/timber-auctions/",
  "/coal-auctions/",
  "/large-scrap-lots/",
  "/closing-soon/",
  "/accessibility/",
  "/pricing/",
  "/scrap-rates/",
  "/developers/",
];
for (const lp of materialLandings) {
  const htmlPath = path.join(outDir, lp.replace(/^\//, ""), "index.html");
  if (fs.existsSync(htmlPath) && !fs.readFileSync(htmlPath, "utf8").includes("noindex")) {
    materialUrls.add(siteUrl(lp));
  }
}

const children = [
  { file: "sitemap-auctions.xml", urls: auctionUrls },
  { file: "sitemap-sources.xml", urls: sourceLandingUrls },
  { file: "sitemap-states.xml", urls: stateUrls },
  { file: "sitemap-materials.xml", urls: materialUrls },
];

for (const child of children) {
  for (const loc of child.urls) {
    if (isMachineUrl(loc)) {
      console.error(`generate-sitemap: refused machine URL in HTML sitemap: ${loc}`);
      process.exit(1);
    }
  }
  writeUrlset(child.file, child.urls, lastmod);
}

const indexBody = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${children
  .map(
    (c) => `  <sitemap>
    <loc>${escapeXml(`${SITE_ROOT}${BASE_PATH}/${c.file}`)}</loc>
    <lastmod>${lastmod}</lastmod>
  </sitemap>`,
  )
  .join("\n")}
</sitemapindex>
`;
fs.writeFileSync(path.join(outDir, "sitemap.xml"), indexBody, "utf8");

const allUrls = [...auctionUrls, ...sourceLandingUrls, ...stateUrls, ...materialUrls].sort();
const byType = { home: 0, detail: 0, landing: 0, state: 0, commerce: 0 };
const bySource = { mstc: 0, "gem-forward": 0, eauction: 0 };
for (const loc of allUrls) {
  byType[classifySitemapUrl(loc)] = (byType[classifySitemapUrl(loc)] ?? 0) + 1;
  const source = loc.match(/\/auctions\/(mstc|gem-forward|eauction)\//)?.[1];
  if (source) bySource[source] = (bySource[source] ?? 0) + 1;
}

const summaryPath = path.join(outDir, "sitemap-summary.json");
fs.writeFileSync(
  summaryPath,
  `${JSON.stringify(
    {
      generated_at: new Date().toISOString(),
      total_urls: allUrls.length,
      by_type: byType,
      by_source: bySource,
      canonical_domain: SITE_ROOT,
      lastmod,
      children: children.map((c) => ({ file: c.file, count: c.urls.size })),
      html_only: true,
    },
    null,
    2,
  )}\n`,
  "utf8",
);

console.log(
  `generate-sitemap: wrote HTML sitemap index (${allUrls.length} URLs across ${children.length} children)`,
);
console.log(`generate-sitemap: wrote ${summaryPath}`);
