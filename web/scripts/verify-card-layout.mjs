#!/usr/bin/env node
/** Lightweight card layout checks on built output */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(__dirname, "..", "out");
const dataJs = path.join(outDir, "data", "auctions-data.js");
const statusIndex = path.join(outDir, "status", "index.html");

const allowEmptyExport = ["1", "true", "yes"].includes(
  String(process.env.PIPELINE_ALLOW_SMALL_EXPORT || "").trim().toLowerCase(),
);

function walkJsFiles(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) walkJsFiles(full, out);
    else if (ent.name.endsWith(".js")) out.push(full);
  }
  return out;
}

function chunkTextIncludes(needle) {
  const files = walkJsFiles(path.join(outDir, "_next"));
  const lower = needle.toLowerCase();
  return files.some((file) => fs.readFileSync(file, "utf8").toLowerCase().includes(lower));
}

const hasImportedAt =
  fs.existsSync(dataJs) && fs.readFileSync(dataJs, "utf8").includes("imported_at");

const checks = [
  [
    "import timestamps in data loader",
    hasImportedAt || allowEmptyExport,
  ],
  [
    "status page exported",
    fs.existsSync(statusIndex) && fs.readFileSync(statusIndex, "utf8").includes("status"),
  ],
  [
    "site disclaimer in client bundle",
    chunkTextIncludes("before bidding"),
  ],
  [
    "card imported label in client bundle",
    chunkTextIncludes("Imported:") || chunkTextIncludes("imported_at"),
  ],
];

let failed = 0;
for (const [label, pass] of checks) {
  console.log(`${pass ? "OK" : "FAIL"}  card/layout: ${label}`);
  if (!pass) failed++;
}
process.exit(failed ? 1 : 0);
