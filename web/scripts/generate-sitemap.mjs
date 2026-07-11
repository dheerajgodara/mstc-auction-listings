#!/usr/bin/env node
/**
 * Generate sitemap.xml from auction-routes.json and known landing pages.
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

const routesPath = path.join(outDir, "data", "auction-routes.json");
if (!fs.existsSync(routesPath)) {
  console.error("generate-sitemap: missing auction-routes.json — run prepare-public-data first");
  process.exit(1);
}

const routesData = readJson(routesPath);
const urls = new Set();

urls.add(siteUrl("/"));

for (const route of routesData.routes ?? []) {
  if (route.indexable === false) continue;
  urls.add(siteUrl(`/${route.source_slug}/${route.route_id}/`));
}

const staticLandings = [
  "/mstc-auctions/",
  "/gem-forward-auctions/",
  "/eauction-gov-in/",
  "/scrap/",
  "/metal-scrap/",
  "/aluminium-scrap/",
  "/vehicle-auctions/",
  "/timber-auctions/",
  "/coal-auctions/",
  "/accessibility/",
  "/pricing/",
];

for (const lp of staticLandings) {
  const htmlPath = path.join(outDir, lp.replace(/^\//, ""), "index.html");
  if (fs.existsSync(htmlPath) && !fs.readFileSync(htmlPath, "utf8").includes("noindex")) {
    urls.add(siteUrl(lp));
  }
}

const stateConfigPath = path.join(webRoot, "public", "data", "seo-state-pages.json");
if (fs.existsSync(stateConfigPath)) {
  const states = readJson(stateConfigPath);
  for (const st of states) {
    const htmlPath = path.join(outDir, "state", st.slug, "index.html");
    if (fs.existsSync(htmlPath)) {
      urls.add(siteUrl(`/state/${st.slug}/`));
    }
  }
}

const lastmod = routesData.automation_ran_at?.slice(0, 10) ?? new Date().toISOString().slice(0, 10);

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

const outPath = path.join(outDir, "sitemap.xml");
fs.writeFileSync(outPath, body, "utf8");

const sortedUrls = [...urls].sort();
const byType = { home: 0, detail: 0, landing: 0, state: 0, commerce: 0 };
const bySource = { mstc: 0, "gem-forward": 0, eauction: 0 };
for (const loc of sortedUrls) {
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
      total_urls: sortedUrls.length,
      by_type: byType,
      by_source: bySource,
      canonical_domain: SITE_ROOT,
      lastmod,
    },
    null,
    2,
  )}\n`,
  "utf8",
);

console.log(`generate-sitemap: wrote ${outPath} with ${urls.size} URLs`);
console.log(`generate-sitemap: wrote ${summaryPath}`);
