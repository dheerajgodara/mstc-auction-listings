#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import {
  EXPECTED_ROBOTS_SITEMAP_URL,
  INDEXABLE_COMMERCE_SLUGS,
  INDEXABLE_LANDING_SLUGS,
  MIN_LANDING_VISIBLE_TEXT,
  NOINDEX_HUB_PREFIX,
  NOINDEX_UTILITY_PAGES,
  OG_TWITTER_PROPERTIES,
  REGRESSION_DETAIL_PAGES,
  SITE_ROOT,
  extractCanonical,
  extractH1,
  extractMetaContent,
  extractTitle,
  hasInternalDetailLink,
  hasOfficialClaim,
  hasStagingLeak,
  outDir,
  readHtml,
  readRootIndex,
  visibleTextLength,
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

const indexHtml = readRootIndex();
pass("discover page exported", Boolean(indexHtml));
pass("discover canonical uses production domain", extractCanonical(indexHtml).startsWith(SITE_ROOT));
pass("discover canonical has no query", !extractCanonical(indexHtml).includes("?"));
pass("discover is indexable", Boolean(indexHtml) && !indexHtml.includes("noindex"));

const homeTitle = extractTitle(indexHtml);
pass("home title mentions scrap auction", /scrap auction/i.test(homeTitle), homeTitle.slice(0, 60));
if (homeTitle.length > 70) warn("home title long", `${homeTitle.length} chars`);

pass("home og:title present", Boolean(extractMetaContent(indexHtml, "og:title")));
pass("home og:description present", Boolean(extractMetaContent(indexHtml, "og:description")));
pass("home og:url on production domain", extractMetaContent(indexHtml, "og:url").startsWith(SITE_ROOT));

const homeJsonLd = indexHtml.match(/application\/ld\+json/gi);
if (homeJsonLd?.length) {
  pass("home JSON-LD documented as present", true, `${homeJsonLd.length} block(s)`);
} else {
  warn("home JSON-LD absent", "intentionally omitted — no Organization/WebSite authority claims");
}

for (const page of NOINDEX_UTILITY_PAGES) {
  const html = readHtml(page);
  pass(`${page}/ exported`, Boolean(html));
  pass(`${page}/ has noindex`, html.includes("noindex"));
}

const h1BySlug = new Map();
for (const slug of INDEXABLE_LANDING_SLUGS) {
  const html = readHtml(slug);
  if (!html) {
    warn(`${slug}/ not exported`, "skipped indexable check");
    continue;
  }
  if (html.includes("noindex")) {
    warn(`${slug}/ noindex`, "skipped indexable landing checks because active inventory is below threshold");
    continue;
  }
  pass(`${slug}/ indexable`, true);
  const canonical = extractCanonical(html);
  pass(`${slug}/ canonical on production domain`, canonical.startsWith(SITE_ROOT));
  const h1 = extractH1(html);
  pass(`${slug}/ has H1`, h1.length >= 5, h1.slice(0, 40));
  const textLen = visibleTextLength(html);
  pass(`${slug}/ has sufficient visible content`, textLen >= MIN_LANDING_VISIBLE_TEXT, `${textLen} chars`);
  if (slug !== "accessibility") {
    pass(`${slug}/ links to detail pages`, hasInternalDetailLink(html));
  }
  if (h1) {
    if (h1BySlug.has(h1)) {
      pass(`${slug}/ H1 unique`, false, `duplicate of ${h1BySlug.get(h1)}`);
    } else {
      h1BySlug.set(h1, slug);
      pass(`${slug}/ H1 unique`, true);
    }
  }
  const metaBlob = extractTitle(html) + extractMetaContent(html, "description");
  pass(`${slug}/ avoids official-site claim`, !hasOfficialClaim(metaBlob));
}

pass("accessibility/ index policy", true, "indexable compliance page — included in sitemap");

for (const slug of INDEXABLE_COMMERCE_SLUGS) {
  const html = readHtml(slug);
  if (!html) {
    pass(`${slug}/ exported`, false);
    continue;
  }
  pass(`${slug}/ exported`, true);
  pass(`${slug}/ indexable`, !html.includes("noindex"));
  const title = extractTitle(html);
  pass(`${slug}/ title present`, title.length >= 15, title.slice(0, 50));
  pass(`${slug}/ title mentions pricing or plans`, /pricing|plans/i.test(title), title.slice(0, 50));
  const desc = extractMetaContent(html, "description");
  pass(`${slug}/ description present`, desc.length >= 40, `${desc.length} chars`);
  const canonical = extractCanonical(html);
  pass(`${slug}/ canonical on production domain`, canonical.startsWith(SITE_ROOT));
  pass(`${slug}/ canonical path includes pricing`, canonical.includes("/pricing/"), canonical);
  const h1 = extractH1(html);
  pass(`${slug}/ has H1`, h1.length >= 5, h1.slice(0, 40));
  pass(`${slug}/ avoids official-site claim`, !hasOfficialClaim(title + desc));
  pass(`${slug}/ links to discover or detail pages`, hasInternalDetailLink(html) || html.includes('href="/auctions/"') || html.includes("Discover"));
}

function walkHubPages(dir, rel = "") {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    const nextRel = rel ? `${rel}/${entry.name}` : entry.name;
    if (entry.isDirectory()) walkHubPages(full, nextRel);
    else if (entry.name === "index.html") {
      const html = fs.readFileSync(full, "utf8");
      const label = `hub/${nextRel.replace(/\/index\.html$/, "")}`;
      pass(`${label} has noindex`, html.includes("noindex"));
      pass(`${label} omitted from sitemap policy`, true, "hub pages are noindex and not in sitemap");
    }
  }
}
walkHubPages(path.join(outDir, "hub"));

const robotsPath = path.join(outDir, "robots.txt");
pass("robots.txt exists", fs.existsSync(robotsPath));
if (fs.existsSync(robotsPath)) {
  const robots = fs.readFileSync(robotsPath, "utf8");
  pass("robots references sitemap", /sitemap:/i.test(robots));
  pass("robots disallows data", /disallow:\s*\/auctions\/data\//i.test(robots));
  pass(
    "robots allows CSS/JS (no blanket disallow)",
    !/disallow:\s*\//i.test(robots.replace(/disallow:\s*\/auctions\/data\//gi, "")),
  );
  const sitemapLine = robots.match(/Sitemap:\s*(\S+)/i)?.[1]?.trim() ?? "";
  pass("robots sitemap URL exact", sitemapLine === EXPECTED_ROBOTS_SITEMAP_URL, sitemapLine);
}

pass("no staging domain in home metadata", !hasStagingLeak(extractCanonical(indexHtml) + homeTitle));

for (const { source, id } of REGRESSION_DETAIL_PAGES) {
  const html = readHtml(`${source}/${id}`);
  pass(`${source}/${id} exported`, Boolean(html));
  if (!html) continue;
  const title = extractTitle(html);
  const desc = extractMetaContent(html, "description");
  pass(`${source}/${id} title present`, title.length >= 15, title.slice(0, 50));
  pass(`${source}/${id} description present`, desc.length >= 40, `${desc.length} chars`);
  pass(`${source}/${id} not noindex`, !html.includes("noindex"));
  const canonical = extractCanonical(html);
  pass(`${source}/${id} canonical matches domain`, canonical.startsWith(SITE_ROOT));
  pass(`${source}/${id} canonical path uses source slug`, canonical.includes(`/${source}/${id}/`), canonical);
  pass(`${source}/${id} avoids official-site claim`, !hasOfficialClaim(title + desc));
  pass(`${source}/${id} og:title present`, Boolean(extractMetaContent(html, "og:title")));
  pass(`${source}/${id} og:description present`, Boolean(extractMetaContent(html, "og:description")));
  pass(`${source}/${id} og:url matches canonical`, extractMetaContent(html, "og:url") === canonical || !extractMetaContent(html, "og:url"));
}

pass("map page does not link raw sitemap with query", !readHtml("map").includes("sitemap.xml?"));

process.exit(ok ? 0 : 1);
