#!/usr/bin/env node
/** GA4 analytics module smoke test (no test runner). */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const analyticsPath = path.join(__dirname, "..", "src", "lib", "analytics.ts");

const src = fs.readFileSync(analyticsPath, "utf8");
const checks = [
  ["NEXT_PUBLIC_GA_MEASUREMENT_ID", src.includes("NEXT_PUBLIC_GA_MEASUREMENT_ID")],
  ["trackEvent", src.includes("trackEvent")],
  ["trackPageView", src.includes("trackPageView")],
  ["gtag guard", src.includes("window.gtag")],
];

let failed = 0;
for (const [label, pass] of checks) {
  console.log(`${pass ? "OK" : "FAIL"}  analytics: ${label}`);
  if (!pass) failed++;
}
process.exit(failed ? 1 : 0);
