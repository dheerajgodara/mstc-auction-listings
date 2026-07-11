#!/usr/bin/env node
/** Verify JSON-LD on exported auction detail pages. */
import {
  DISALLOWED_SCHEMA_TYPES,
  REGRESSION_DETAIL_PAGES,
  SITE_ROOT,
  collectSchemaTypes,
  extractCanonical,
  extractJsonLdBlocks,
  hasStagingLeak,
  readHtml,
  readRootIndex,
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

const homeHtml = readRootIndex();
const homeBlocks = extractJsonLdBlocks(homeHtml);
if (homeBlocks.length === 0) {
  warn("home JSON-LD absent", "intentionally omitted — no Organization/WebSite authority schema");
} else {
  for (const raw of homeBlocks) {
    try {
      const parsed = JSON.parse(raw);
      const types = collectSchemaTypes(parsed);
      pass("home JSON-LD avoids disallowed types", !types.some((t) => DISALLOWED_SCHEMA_TYPES.includes(t)), types.join(", "));
    } catch {
      pass("home JSON-LD parses", false);
    }
  }
}

for (const { source, id } of REGRESSION_DETAIL_PAGES) {
  const label = `${source}/${id}`;
  const html = readHtml(`${source}/${id}`);
  pass(`${label} exported`, Boolean(html));
  if (!html) continue;

  const blocks = extractJsonLdBlocks(html);
  pass(`${label} has JSON-LD`, blocks.length > 0, `${blocks.length} block(s)`);

  const canonical = extractCanonical(html);
  let hasEvent = false;
  let hasBreadcrumb = false;
  const schemaTypes = new Set();

  for (const raw of blocks) {
    pass(`${label} JSON-LD parses`, (() => {
      try {
        JSON.parse(raw);
        return true;
      } catch {
        return false;
      }
    })());

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      continue;
    }

    for (const t of collectSchemaTypes(parsed)) schemaTypes.add(t);
    const disallowed = [...schemaTypes].filter((t) => DISALLOWED_SCHEMA_TYPES.includes(t));
    pass(`${label} no disallowed schema types`, disallowed.length === 0, disallowed.join(", ") || [...schemaTypes].join(", "));

    if (parsed["@type"] === "Event") {
      hasEvent = true;
      pass(`${label} Event has name`, Boolean(parsed.name));
      pass(`${label} Event url matches canonical`, parsed.url === canonical, parsed.url ?? "missing");
      pass(`${label} Event url on production domain`, String(parsed.url ?? "").startsWith(SITE_ROOT));
      if (parsed.offers) {
        pass(`${label} Offer has numeric price when present`, typeof parsed.offers.price === "number");
      }
      if (parsed.startDate) pass(`${label} startDate ISO-like`, /^\d{4}-\d{2}-\d{2}/.test(String(parsed.startDate)));
      if (parsed.endDate) pass(`${label} endDate ISO-like`, /^\d{4}-\d{2}-\d{2}/.test(String(parsed.endDate)));
    }
    if (parsed["@type"] === "BreadcrumbList") {
      hasBreadcrumb = true;
      pass(`${label} BreadcrumbList has items`, Array.isArray(parsed.itemListElement) && parsed.itemListElement.length >= 3);
      for (const item of parsed.itemListElement ?? []) {
        const itemUrl = item?.item;
        if (!itemUrl) continue;
        pass(`${label} Breadcrumb item on production domain`, String(itemUrl).startsWith(SITE_ROOT), String(itemUrl));
        pass(`${label} Breadcrumb item has no query`, !String(itemUrl).includes("?"), String(itemUrl));
        pass(`${label} Breadcrumb item no staging leak`, !hasStagingLeak(String(itemUrl)), String(itemUrl));
      }
    }
    if (parsed["@type"] === "ItemList") {
      pass(`${label} ItemList conservative`, !parsed.aggregateRating && !parsed.review);
    }
  }

  pass(`${label} has Event schema`, hasEvent);
  pass(`${label} has BreadcrumbList schema`, hasBreadcrumb);
}

process.exit(ok ? 0 : 1);
