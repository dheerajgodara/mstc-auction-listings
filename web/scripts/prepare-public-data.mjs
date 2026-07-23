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

// T-30 archive companion (optional — empty shell if missing).
const publicArchiveJson = path.join(webRoot, "public", "data", "archive-auctions.json");
const outArchiveJson = path.join(outDataDir, "archive-auctions.json");
let archiveData = {
  generated_at: data.generated_at || new Date().toISOString(),
  count: 0,
  auctions: [],
  stats: { archive: true },
  schema_version: 1,
};
if (fs.existsSync(publicArchiveJson)) {
  archiveData = readJson(publicArchiveJson);
}
fs.writeFileSync(outArchiveJson, JSON.stringify(archiveData, null, 2), "utf8");
if (!fs.existsSync(publicArchiveJson)) {
  fs.writeFileSync(publicArchiveJson, JSON.stringify(archiveData, null, 2) + "\n", "utf8");
}
const archiveJsPath = path.join(outDataDir, "archive-auctions-data.js");
fs.writeFileSync(
  archiveJsPath,
  `window.__ARCHIVE_AUCTIONS_EXPORT__ = ${JSON.stringify(archiveData)};\n`,
  "utf8",
);
const publicArchiveJs = path.join(webRoot, "public", "data", "archive-auctions-data.js");
fs.writeFileSync(
  publicArchiveJs,
  `window.__ARCHIVE_AUCTIONS_EXPORT__ = ${JSON.stringify(archiveData)};\n`,
  "utf8",
);

const dataVersion = data.run_id || data.automation_ran_at;
const meta = {
  automation_ran_at: data.automation_ran_at,
  export_generated_at: data.export_generated_at ?? data.generated_at,
  run_id: data.run_id ?? dataVersion,
  count: data.count ?? data.auctions?.length ?? 0,
  archive_count: archiveData.count ?? archiveData.auctions?.length ?? 0,
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
// HTML sitemap index is written by generate-sitemap.mjs (after generate-machine-layer).
