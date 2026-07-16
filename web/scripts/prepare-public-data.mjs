#!/usr/bin/env node
/**
 * Post-build: sync finalized export into out/ and emit auctions-data.js + export-meta.json.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDataDir = path.join(webRoot, "out", "data");
const publicJson = path.join(webRoot, "public", "data", "auctions.json");
const outJson = path.join(outDataDir, "auctions.json");

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function pickSourcePath() {
  const candidates = [];
  if (fs.existsSync(publicJson)) candidates.push(publicJson);
  if (fs.existsSync(outJson)) candidates.push(outJson);
  if (!candidates.length) return null;

  // Prefer export that has import-tracking metadata (post-finalize).
  const scored = candidates.map((p) => {
    const data = readJson(p);
    const hasAutomation = Boolean(data.automation_ran_at);
    const missingImport = (data.auctions || []).filter(
      (a) => !(a.imported_at || a.first_seen_at),
    ).length;
    return { path: p, data, hasAutomation, missingImport };
  });

  scored.sort((a, b) => {
    if (a.hasAutomation !== b.hasAutomation) return a.hasAutomation ? -1 : 1;
    if (a.missingImport !== b.missingImport) return a.missingImport - b.missingImport;
    return 0;
  });

  return scored[0];
}

const picked = pickSourcePath();
if (!picked) {
  console.error("No auctions.json found for prepare-public-data");
  process.exit(1);
}

const { path: sourcePath, data } = picked;
fs.mkdirSync(outDataDir, { recursive: true });
fs.writeFileSync(outJson, JSON.stringify(data, null, 2), "utf8");

const missingImport = (data.auctions || []).filter(
  (a) => !(a.imported_at || a.first_seen_at),
).length;
if (!data.automation_ran_at) {
  console.error("prepare-public-data: automation_ran_at missing — run finalize_public_export first");
  process.exit(1);
}
if (missingImport > 0) {
  console.error(
    `prepare-public-data: ${missingImport} auctions missing imported_at/first_seen_at`,
  );
  process.exit(1);
}

const jsPath = path.join(outDataDir, "auctions-data.js");
const jsBody = `window.__AUCTIONS_EXPORT__ = ${JSON.stringify(data)};\n`;
fs.writeFileSync(jsPath, jsBody, "utf8");

const dataVersion = data.run_id || data.automation_ran_at;
const meta = {
  automation_ran_at: data.automation_ran_at,
  export_generated_at: data.export_generated_at ?? data.generated_at,
  run_id: data.run_id ?? dataVersion,
  count: data.count ?? data.auctions?.length ?? 0,
  data_version: dataVersion,
};
const metaPath = path.join(outDataDir, "export-meta.json");
fs.writeFileSync(metaPath, `${JSON.stringify(meta, null, 2)}\n`, "utf8");

// Keep public export-meta in sync for dev/next static copy on future builds.
const publicMetaPath = path.join(webRoot, "public", "data", "export-meta.json");
fs.writeFileSync(publicMetaPath, `${JSON.stringify(meta, null, 2)}\n`, "utf8");

const centroidsPublic = path.join(webRoot, "public", "data", "city-centroids.json");
const centroidsOut = path.join(outDataDir, "city-centroids.json");
if (fs.existsSync(centroidsPublic)) {
  fs.copyFileSync(centroidsPublic, centroidsOut);
} else {
  console.error("prepare-public-data: missing public/data/city-centroids.json — run generate-city-centroids");
  process.exit(1);
}

const jsonBytes = fs.statSync(sourcePath).size;
const jsBytes = fs.statSync(jsPath).size;
console.log(
  `prepare-public-data: wrote ${jsPath} (${jsBytes} bytes) from ${sourcePath} (${jsonBytes} bytes), ${meta.count} auctions`,
);

// Minimal production sitemap so post-deploy HTTP verify and crawlers have a live map.
// Detail pages are client-routed today; include discover + status only.
const siteRoot = "https://scrapauctionindia.com/auctions";
const lastmod = String(data.automation_ran_at || data.generated_at || new Date().toISOString()).slice(0, 10);
const sitemapUrls = [
  { loc: `${siteRoot}/`, priority: "1.0" },
  { loc: `${siteRoot}/status/`, priority: "0.3" },
];
const sitemapXml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemapUrls
  .map(
    (u) => `  <url>
    <loc>${u.loc}</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>${u.priority}</priority>
  </url>`,
  )
  .join("\n")}
</urlset>
`;
const sitemapPath = path.join(webRoot, "out", "sitemap.xml");
fs.writeFileSync(sitemapPath, sitemapXml, "utf8");
console.log(`prepare-public-data: wrote ${sitemapPath} (${sitemapUrls.length} URLs)`);
