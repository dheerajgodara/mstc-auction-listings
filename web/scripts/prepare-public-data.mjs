#!/usr/bin/env node
/**
 * Post-build: emit Hostinger-friendly auctions-data.js alongside auctions.json.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDataDir = path.join(webRoot, "out", "data");
const publicJson = path.join(webRoot, "public", "data", "auctions.json");
const outJson = path.join(outDataDir, "auctions.json");

let sourcePath = outJson;
if (!fs.existsSync(sourcePath) && fs.existsSync(publicJson)) {
  sourcePath = publicJson;
  fs.mkdirSync(outDataDir, { recursive: true });
  fs.copyFileSync(publicJson, outJson);
}

if (!fs.existsSync(sourcePath)) {
  console.error("No auctions.json found for prepare-public-data");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
const jsPath = path.join(outDataDir, "auctions-data.js");
const jsBody = `window.__AUCTIONS_EXPORT__ = ${JSON.stringify(data)};\n`;
fs.writeFileSync(jsPath, jsBody, "utf8");

const jsonBytes = fs.statSync(sourcePath).size;
const jsBytes = fs.statSync(jsPath).size;
console.log(`prepare-public-data: wrote ${jsPath} (${jsBytes} bytes) from JSON (${jsonBytes} bytes)`);
