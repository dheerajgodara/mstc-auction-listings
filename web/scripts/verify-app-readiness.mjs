#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");
const checks = [];

function ok(label, pass, detail = "") {
  checks.push({ label, pass, detail });
  console.log(`${pass ? "OK" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
}

function read(file) {
  return fs.readFileSync(file, "utf8");
}

const manifestPath = path.join(outDir, "manifest.webmanifest");
ok("manifest.webmanifest exported", fs.existsSync(manifestPath));

if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(read(manifestPath));
  ok("manifest name is Scrap Auction India", manifest.name === "Scrap Auction India");
  ok("manifest start_url scoped to /auctions", String(manifest.start_url || "").startsWith("/auctions/"));
  ok("manifest scope is /auctions/", manifest.scope === "/auctions/");
  ok("manifest display is standalone", manifest.display === "standalone");
  ok("manifest has icons", Array.isArray(manifest.icons) && manifest.icons.length >= 2);
  ok("manifest has app shortcuts", Array.isArray(manifest.shortcuts) && manifest.shortcuts.length >= 3);
}

const swPath = path.join(outDir, "sw.js");
ok("service worker exported", fs.existsSync(swPath));
if (fs.existsSync(swPath)) {
  const sw = read(swPath);
  ok("service worker is base-path aware", sw.includes("self.registration.scope"));
  ok("service worker avoids stale auctions-data cache", sw.includes("/data/auctions-data.js") && sw.includes("no-store"));
  ok("service worker caches app shell route", sw.includes('scopePath("app/")'));
}

const appPagePath = path.join(outDir, "app", "index.html");
ok("app install page exported", fs.existsSync(appPagePath));
if (fs.existsSync(appPagePath)) {
  const appHtml = read(appPagePath);
  ok("app page has noindex", appHtml.includes("noindex"));
  ok("app page references install copy", appHtml.includes("Install Scrap Auction India"));
}

const layoutPath = path.join(webRoot, "src", "app", "layout.tsx");
const layout = read(layoutPath);
ok("root layout references manifest", layout.includes("manifest:"));
ok("root layout registers service worker", layout.includes("<ServiceWorkerRegister />"));
ok("root layout has web app metadata", layout.includes("appleWebApp"));

const footerPath = path.join(webRoot, "src", "components", "site-footer.tsx");
ok("footer links install app", read(footerPath).includes("Install app"));

const failed = checks.filter((check) => !check.pass);
if (failed.length) process.exit(1);
