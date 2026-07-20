#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import {
  FORBIDDEN_SITEMAP_ASSET_PATHS,
  FORBIDDEN_SITEMAP_UTILITY_PATHS,
  NOINDEX_UTILITY_PAGES,
  resolveRegressionDetailPages,
  SITE_ROOT,
  STAGING_DOMAIN_MARKERS,
  classifySitemapUrl,
  collectHtmlSitemapUrls,
  detailSourceFromSitemapUrl,
  htmlPathForSitemapUrl,
  isSitemapIndex,
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
  pass("sitemap is HTML sitemap index", isSitemapIndex(xml));
  pass("sitemap uses production domain", xml.includes(SITE_ROOT));
  pass("sitemap index references sitemap-auctions.xml", xml.includes("sitemap-auctions.xml"));
  pass("sitemap index references sitemap-sources.xml", xml.includes("sitemap-sources.xml"));
  pass("sitemap index references sitemap-states.xml", xml.includes("sitemap-states.xml"));
  pass("sitemap index references sitemap-materials.xml", xml.includes("sitemap-materials.xml"));
  pass("sitemap index excludes machine-sitemap", !xml.includes("machine-sitemap"));

  for (const marker of STAGING_DOMAIN_MARKERS) {
    pass(`sitemap excludes staging marker: ${marker}`, !xml.toLowerCase().includes(marker));
  }

  const childFiles = [
    "sitemap-auctions.xml",
    "sitemap-sources.xml",
    "sitemap-states.xml",
    "sitemap-materials.xml",
  ];
  for (const file of childFiles) {
    pass(`${file} exists`, fs.existsSync(path.join(outDir, file)));
  }

  const urls = collectHtmlSitemapUrls();
  pass("sitemap has discover URL", urls.some((u) => u === `${SITE_ROOT}/auctions/` || u === `${SITE_ROOT}/auctions`));
  pass("sitemap excludes query strings", !urls.some((u) => u.includes("?q=") || u.includes("?source=")));
  pass("sitemap URL count", urls.length > 100, String(urls.length));
  pass(
    "HTML sitemap has no /api/ or /feeds/",
    !urls.some((u) => u.includes("/api/") || u.includes("/feeds/")),
  );

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
  pass(
    "sitemap includes developers URL",
    urls.some((u) => u.includes("/developers/")),
  );
  pass("sitemap includes MSTC detail URLs", bySource.mstc > 50, String(bySource.mstc));
  // GeM is optional during MSTC-first refill after a ledger wipe / fresh start.
  if ((bySource["gem-forward"] ?? 0) >= 1) {
    pass(
      "sitemap includes GeM Forward detail URLs",
      true,
      String(bySource["gem-forward"]),
    );
  } else {
    warn(
      "sitemap GeM Forward detail URLs empty (warn-only until GeM publishable)",
      String(bySource["gem-forward"] ?? 0),
    );
  }
  if (bySource.eauction >= 1) {
    pass("sitemap includes eAuction detail URLs", true, String(bySource.eauction));
  } else {
    warn("sitemap eAuction detail URLs empty (warn-only)", String(bySource.eauction));
  }
  pass(
    "sitemap excludes noindex utility URLs",
    forbiddenHits.filter((h) => h.violations.some((v) => v.type === "utility")).length === 0,
    forbiddenHits.length ? forbiddenHits.slice(0, 3).map((h) => h.loc).join(", ") : "",
  );
  pass(
    "sitemap excludes raw asset paths",
    forbiddenHits.filter((h) => h.violations.some((v) => v.type === "asset")).length === 0,
  );
  pass(
    "sitemap excludes hub URLs",
    forbiddenHits.filter((h) => h.violations.some((v) => v.type === "hub")).length === 0,
  );

  for (const segment of FORBIDDEN_SITEMAP_UTILITY_PATHS) {
    pass(`sitemap has no ${segment}`, !urls.some((u) => u.includes(segment)));
  }
  for (const slug of NOINDEX_UTILITY_PAGES) {
    pass(`sitemap excludes noindex utility /${slug}/`, !urls.some((u) => u.includes(`/${slug}/`)));
  }
  for (const segment of FORBIDDEN_SITEMAP_ASSET_PATHS) {
    pass(`sitemap has no ${segment}`, !urls.some((u) => u.includes(segment)));
  }

  const regressionPages = resolveRegressionDetailPages(2);
  pass(
    "regression detail pages available for sitemap checks",
    regressionPages.length >= 1,
    regressionPages.map((p) => `${p.source}/${p.id}`).join(", ") || "none",
  );
  for (const { source, id } of regressionPages) {
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
      pass(
        `sitemap ${src} count matches routes`,
        deltaSrc <= 2,
        `sitemap ${bySource[src]}, routes ${routeMix[src]}`,
      );
    }
  }

  pass("sitemap-summary.json exists", fs.existsSync(path.join(outDir, "sitemap-summary.json")));

  // Child lastmod presence
  for (const file of childFiles) {
    const childPath = path.join(outDir, file);
    if (!fs.existsSync(childPath)) continue;
    const childXml = fs.readFileSync(childPath, "utf8");
    pass(`${file} is urlset`, childXml.includes("<urlset") && childXml.includes("</urlset>"));
    pass(`${file} has lastmod`, childXml.includes("<lastmod>"));
    const childUrls = sitemapUrlsFromXml(childXml);
    pass(
      `${file} has no machine URLs`,
      !childUrls.some((u) => u.includes("/api/") || u.includes("/feeds/")),
    );
  }
}

process.exit(ok ? 0 : 1);
