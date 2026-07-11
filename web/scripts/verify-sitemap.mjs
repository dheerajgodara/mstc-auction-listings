#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import {
  EXPECTED_ROBOTS_SITEMAP_URL,
  FORBIDDEN_SITEMAP_ASSET_PATHS,
  FORBIDDEN_SITEMAP_UTILITY_PATHS,
  INDEXABLE_LANDING_SLUGS,
  NOINDEX_UTILITY_PAGES,
  REGRESSION_DETAIL_PAGES,
  SITE_ROOT,
  STAGING_DOMAIN_MARKERS,
  classifySitemapUrl,
  detailSourceFromSitemapUrl,
  extractCanonical,
  hasStagingLeak,
  htmlPathForSitemapUrl,
  outDir,
  sitemapUrlViolations,
  sitemapUrlsFromXml,
} from "./seo-lib.mjs";

let ok = true;
function pass(label, cond, detail = "") {
  const mark = cond ? "OK" : "FAIL";
  if (!cond) ok = false;
  console.log(`${mark}  ${label}${detail ? ` — ${detail}` : ""}`);
}

function warn(label, detail = "") {
  console.log(`WARN ${label}${detail ? ` — ${detail}` : ""}`);
}

const sitemapPath = path.join(outDir, "sitemap.xml");
pass("sitemap.xml exists", fs.existsSync(sitemapPath));

if (fs.existsSync(sitemapPath)) {
  const xml = fs.readFileSync(sitemapPath, "utf8");
  pass("sitemap valid urlset", xml.includes("<urlset") && xml.includes("</urlset>"));
  pass("sitemap uses production domain", xml.includes(SITE_ROOT));
  pass("sitemap has discover URL", xml.includes(`${SITE_ROOT}/auctions/`));
  pass("sitemap excludes query strings", !xml.includes("?q=") && !xml.includes("?source="));
  pass("sitemap has lastmod", xml.includes("<lastmod>"));

  for (const marker of STAGING_DOMAIN_MARKERS) {
    pass(`sitemap excludes staging marker: ${marker}`, !xml.toLowerCase().includes(marker));
  }

  const urls = sitemapUrlsFromXml(xml);
  pass("sitemap URL count", urls.length > 100, String(urls.length));

  const byType = { home: 0, detail: 0, landing: 0, state: 0, commerce: 0 };
  const bySource = { mstc: 0, "gem-forward": 0, eauction: 0 };
  const forbiddenHits = [];

  for (const loc of urls) {
    byType[classifySitemapUrl(loc)] += 1;
    const src = detailSourceFromSitemapUrl(loc);
    if (src) bySource[src] = (bySource[src] ?? 0) + 1;
    const violations = sitemapUrlViolations(loc);
    if (violations.length > 0) forbiddenHits.push({ loc, violations });
  }

  pass("sitemap includes home", byType.home >= 1, String(byType.home));
  pass("sitemap includes detail pages", byType.detail > 50, String(byType.detail));
  pass("sitemap includes landing pages", byType.landing >= 5, String(byType.landing));
  pass("sitemap includes pricing page", byType.commerce >= 1, String(byType.commerce));
  pass(
    "sitemap includes pricing URL",
    urls.some((u) => u.includes("/pricing/")),
  );
  pass("sitemap includes MSTC detail URLs", bySource.mstc > 50, String(bySource.mstc));
  pass("sitemap includes GeM Forward detail URLs", bySource["gem-forward"] >= 1, String(bySource["gem-forward"]));
  pass("sitemap includes eAuction detail URLs", bySource.eauction >= 1, String(bySource.eauction));

  pass("sitemap excludes noindex utility URLs", forbiddenHits.filter((h) => h.violations.some((v) => v.type === "utility")).length === 0,
    forbiddenHits.length ? forbiddenHits.slice(0, 3).map((h) => h.loc).join(", ") : "");
  pass("sitemap excludes raw asset paths", forbiddenHits.filter((h) => h.violations.some((v) => v.type === "asset")).length === 0);
  pass("sitemap excludes hub URLs", forbiddenHits.filter((h) => h.violations.some((v) => v.type === "hub")).length === 0);

  for (const segment of FORBIDDEN_SITEMAP_UTILITY_PATHS) {
    pass(`sitemap has no ${segment}`, !urls.some((u) => u.includes(segment)));
  }
  for (const slug of NOINDEX_UTILITY_PAGES) {
    pass(`sitemap excludes noindex utility /${slug}/`, !urls.some((u) => u.includes(`/${slug}/`)));
  }
  for (const segment of FORBIDDEN_SITEMAP_ASSET_PATHS) {
    pass(`sitemap has no ${segment}`, !urls.some((u) => u.includes(segment)));
  }

  for (const { source, id } of REGRESSION_DETAIL_PAGES) {
    const expected = `${SITE_ROOT}/auctions/${source}/${id}/`;
    pass(`sitemap includes regression ${source}/${id}`, urls.includes(expected));
  }

  let missingHtml = 0;
  for (const loc of urls) {
    const htmlPath = htmlPathForSitemapUrl(loc);
    if (htmlPath && !fs.existsSync(htmlPath)) missingHtml++;
  }
  pass("sitemap URLs have built HTML", missingHtml === 0, missingHtml ? `${missingHtml} missing` : "");

  const routesPath = path.join(outDir, "data", "auction-routes.json");
  if (fs.existsSync(routesPath)) {
    const routesData = JSON.parse(fs.readFileSync(routesPath, "utf8"));
    const expected = (routesData.routes ?? []).filter((r) => r.indexable !== false).length;
    const delta = Math.abs(byType.detail - expected);
    pass(
      "sitemap detail count matches routes",
      delta <= 2,
      `sitemap ${byType.detail}, routes ${expected}`,
    );
    const routeMix = { mstc: 0, "gem-forward": 0, eauction: 0 };
    for (const route of routesData.routes ?? []) {
      if (route.indexable === false) continue;
      const slug = route.source_slug;
      if (slug in routeMix) routeMix[slug] += 1;
    }
    for (const src of ["mstc", "gem-forward", "eauction"]) {
      const deltaSrc = Math.abs((bySource[src] ?? 0) - (routeMix[src] ?? 0));
      pass(`sitemap ${src} count matches routes`, deltaSrc <= 2, `sitemap ${bySource[src]}, routes ${routeMix[src]}`);
    }
  }

  pass("sitemap-summary.json exists", fs.existsSync(path.join(outDir, "sitemap-summary.json")));
}

process.exit(ok ? 0 : 1);
