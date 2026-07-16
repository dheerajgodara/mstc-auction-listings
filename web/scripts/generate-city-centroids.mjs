#!/usr/bin/env node
/**
 * Build data/city-centroids.json from static Indian city/state coords + live export.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  CITY_CENTROIDS,
  STATE_CENTROIDS,
  normalizeCentroidKey,
} from "./city-centroid-data.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const auctionsPath = path.join(webRoot, "public", "data", "auctions.json");
const outPath = path.join(webRoot, "public", "data", "city-centroids.json");

function readAuctions() {
  if (!fs.existsSync(auctionsPath)) {
    console.warn(`generate-city-centroids: ${auctionsPath} missing; using static coords only`);
    return [];
  }
  const data = JSON.parse(fs.readFileSync(auctionsPath, "utf8"));
  return data.auctions ?? [];
}

function lookupStatic(key) {
  const normalized = normalizeCentroidKey(key);
  if (!normalized) return null;
  return CITY_CENTROIDS[normalized] ?? STATE_CENTROIDS[normalized] ?? null;
}

function buildCentroids(auctions) {
  /** @type {Record<string, { lat: number; lng: number }>} */
  const centroids = {};

  for (const [key, coord] of Object.entries(STATE_CENTROIDS)) {
    centroids[normalizeCentroidKey(key)] = coord;
  }
  for (const [key, coord] of Object.entries(CITY_CENTROIDS)) {
    centroids[normalizeCentroidKey(key)] = coord;
  }

  let mappedFromExport = 0;
  let stateFallback = 0;

  for (const auction of auctions) {
    const city = auction.display_location_city;
    const state = auction.display_location_state ?? auction.state;
    const location = auction.location;

    for (const candidate of [city, location, state, auction.region]) {
      if (!candidate) continue;
      const key = normalizeCentroidKey(candidate);
      if (!key || centroids[key]) continue;
      const direct = lookupStatic(candidate);
      if (direct) {
        centroids[key] = direct;
        mappedFromExport += 1;
        continue;
      }
    }

    if (!city) continue;
    const cityKey = normalizeCentroidKey(city);
    if (centroids[cityKey]) continue;

    const stateKey = normalizeCentroidKey(state);
    if (stateKey && centroids[stateKey]) {
      centroids[cityKey] = centroids[stateKey];
      stateFallback += 1;
      continue;
    }

    // Partial match: city name contains a known city token.
    for (const [known, coord] of Object.entries(CITY_CENTROIDS)) {
      if (cityKey.includes(known) || known.includes(cityKey)) {
        centroids[cityKey] = coord;
        mappedFromExport += 1;
        break;
      }
    }
  }

  return { centroids, mappedFromExport, stateFallback };
}

function countCoverage(auctions, centroids) {
  let withCity = 0;
  let geocoded = 0;
  for (const auction of auctions) {
    if (!auction.display_location_city) continue;
    withCity += 1;
    const candidates = [
      auction.display_location_city,
      auction.location,
      auction.display_location_state,
      auction.state,
      auction.region,
    ];
    const hit = candidates.some((c) => {
      const key = normalizeCentroidKey(c);
      return key && centroids[key];
    });
    if (hit) geocoded += 1;
  }
  return { withCity, geocoded };
}

const auctions = readAuctions();
const { centroids, mappedFromExport, stateFallback } = buildCentroids(auctions);
const coverage = countCoverage(auctions, centroids);

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, `${JSON.stringify(centroids, null, 2)}\n`, "utf8");

console.log(
  `generate-city-centroids: wrote ${outPath} (${Object.keys(centroids).length} keys; export-mapped=${mappedFromExport}; state-fallback=${stateFallback}; geocoded=${coverage.geocoded}/${coverage.withCity})`,
);

if (coverage.withCity > 0 && coverage.geocoded / coverage.withCity < 0.5) {
  console.warn(
    `generate-city-centroids: low geocode coverage ${coverage.geocoded}/${coverage.withCity}`,
  );
  process.exit(1);
}
