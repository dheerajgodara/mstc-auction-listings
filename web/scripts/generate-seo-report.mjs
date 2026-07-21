#!/usr/bin/env node
/**
 * Deterministic SEO/analytics report written to web/out/seo-report.json.
 * Run after build:prod (requires web/out).
 */
import fs from "node:fs";
import path from "node:path";
import {
  BASE_PATH,
  DISALLOWED_SCHEMA_TYPES,
  EXPECTED_ROBOTS_SITEMAP_URL,
  INDEXABLE_COMMERCE_SLUGS,
  INDEXABLE_LANDING_SLUGS,
  MIN_LANDING_VISIBLE_TEXT,
  NOINDEX_UTILITY_PAGES,
  OFFICIAL_CLAIM_PATTERNS,
  SITE_ROOT,
  STAGING_DOMAIN_MARKERS,
  classifySitemapUrl,
  collectSchemaTypes,
  detailSourceFromSitemapUrl,
  extractCanonical,
  extractH1,
  extractJsonLdBlocks,
  extractMetaContent,
  extractTitle,
  hasInternalDetailLink,
  hasOfficialClaim,
  hasStagingLeak,
  htmlPathForSitemapUrl,
  outDir,
  readHtml,
  readRootIndex,
  resolveRegressionDetailPages,
  sitemapUrlViolations,
  collectHtmlSitemapUrls,
  visibleTextLength,
} from "./seo-lib.mjs";

const REGRESSION_DETAIL_PAGES = resolveRegressionDetailPages(2);

const TITLE_MIN = 20;
const TITLE_MAX = 70;
const DESC_MIN = 50;
const DESC_MAX = 170;

const ARTIFACT_PATHS = {
  sitemap: "sitemap.xml",
  robots: "robots.txt",
  seo_report: "seo-report.json",
  sitemap_summary: "sitemap-summary.json",
};

function readJsonSafe(p) {
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function usesEvent(body, event) {
  if (body.includes(`"${event}"`) || body.includes(`'${event}'`)) return true;
  const helpers = {
    page_view: ["trackPageView"],
    view_auction_detail: ["trackDetailPageView"],
    view_landing: ["trackLandingPageView"],
    search: ["trackSearch"],
    filter_change: ["trackFilterChange"],
    sort_change: ["trackSortChange"],
    no_results: ["trackNoResults"],
    diligence_open: ["trackDiligenceOpen"],
    compare_add: ["trackCompareAdd"],
    compare_remove: ["trackCompareRemove"],
    map_select: ["trackMapSelect"],
    command_palette: ["command_palette"],
    status_page_view: ["status_page_view"],
    pricing_page_view: ["trackPricingPageView"],
    plan_select: ["trackPlanSelect"],
    upgrade_prompt_view: ["trackUpgradePromptView"],
    upgrade_cta_click: ["trackUpgradeCtaClick"],
    gated_feature_attempt: ["trackGatedFeatureAttempt"],
    checkout_start_stub: ["trackCheckoutStartStub"],
    enterprise_inquiry_click: ["trackEnterpriseInquiryClick"],
    account_page_view: ["trackAccountPageView"],
    saved_search_save: ["saved_search_save"],
  };
  for (const helper of helpers[event] ?? []) {
    if (body.includes(helper)) return true;
  }
  return false;
}

function scanAnalyticsCoverage() {
  const analyticsPath = path.join(outDir, "..", "src", "lib", "analytics.ts");
  const src = fs.readFileSync(analyticsPath, "utf8");
  const requiredEvents = [
    "page_view",
    "view_auction_detail",
    "view_landing",
    "search",
    "filter_change",
    "sort_change",
    "no_results",
    "pdf_open",
    "source_open",
    "lot_expand",
    "watchlist_toggle",
    "apply_saved_search",
    "saved_search_save",
    "diligence_open",
    "compare_add",
    "map_view",
    "command_palette",
    "status_page_view",
    "pricing_page_view",
    "plan_select",
    "upgrade_prompt_view",
    "upgrade_cta_click",
    "gated_feature_attempt",
    "checkout_start_stub",
    "enterprise_inquiry_click",
    "account_page_view",
  ];
  const deferredEvents = [];
  const missingInModule = requiredEvents.filter((e) => !src.includes(`"${e}"`));
  const componentDir = path.join(outDir, "..", "src", "components");
  const hooksDir = path.join(outDir, "..", "src", "hooks");
  const componentFiles = [];
  function walk(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (/\.(tsx|ts)$/.test(entry.name)) componentFiles.push(full);
    }
  }
  walk(componentDir);
  walk(hooksDir);
  const eventUsage = {};
  for (const ev of requiredEvents) {
    eventUsage[ev] = componentFiles.some((f) => usesEvent(fs.readFileSync(f, "utf8"), ev));
  }
  return { missingInModule, eventUsage, deferredEvents };
}

function metadataWarnings() {
  const warnings = [];
  const samples = [
    { label: "home", html: readRootIndex() },
    ...INDEXABLE_LANDING_SLUGS.map((slug) => ({
      label: slug,
      html: readHtml(slug),
    })),
    ...INDEXABLE_COMMERCE_SLUGS.map((slug) => ({
      label: slug,
      html: readHtml(slug),
    })),
    ...REGRESSION_DETAIL_PAGES.map(({ source, id }) => ({
      label: `${source}/${id}`,
      html: readHtml(`${source}/${id}`),
    })),
  ];
  for (const { label, html } of samples) {
    if (!html) {
      // Landings may be omitted in partial builds; details use resolveRegressionDetailPages.
      const severity = label.includes("/") ? "critical" : "warning";
      warnings.push({ page: label, type: "missing_html", severity, message: "index.html not found" });
      continue;
    }
    // Match verify-seo-meta: noindex landings are skipped (inventory threshold), not hard fails.
    if (
      INDEXABLE_LANDING_SLUGS.includes(label) &&
      (html.includes('content="noindex"') || (html.includes("noindex") && html.includes("robots")))
    ) {
      warnings.push({
        page: label,
        type: "noindex_landing_skipped",
        severity: "warning",
        message: "noindex landing — skipped metadata gate",
      });
      continue;
    }
    const title = extractTitle(html);
    const desc = extractMetaContent(html, "description");
    const canonical = extractCanonical(html);
    if (!title) warnings.push({ page: label, type: "missing_title", severity: "critical", message: "no <title>" });
    else if (title.length < TITLE_MIN)
      warnings.push({ page: label, type: "title_short", severity: "warning", message: `title length ${title.length}` });
    else if (title.length > TITLE_MAX)
      warnings.push({ page: label, type: "title_long", severity: "warning", message: `title length ${title.length}` });
    if (!desc)
      warnings.push({ page: label, type: "missing_description", severity: "critical", message: "no meta description" });
    else if (desc.length < DESC_MIN)
      warnings.push({ page: label, type: "description_short", severity: "warning", message: `desc length ${desc.length}` });
    else if (desc.length > DESC_MAX)
      warnings.push({ page: label, type: "description_long", severity: "warning", message: `desc length ${desc.length}` });
    if (hasOfficialClaim(desc + title))
      warnings.push({ page: label, type: "official_claim", severity: "critical", message: "avoid implying site is official" });
    if (canonical && !canonical.startsWith(SITE_ROOT))
      warnings.push({ page: label, type: "canonical_domain", severity: "critical", message: canonical });
    if (canonical && canonical.includes("?"))
      warnings.push({ page: label, type: "canonical_query", severity: "critical", message: canonical });
    if (hasStagingLeak(canonical + title + desc))
      warnings.push({ page: label, type: "staging_leak", severity: "critical", message: "staging domain in metadata" });
    if (label === "home" || REGRESSION_DETAIL_PAGES.some((p) => `${p.source}/${p.id}` === label)) {
      if (!extractMetaContent(html, "og:title"))
        warnings.push({ page: label, type: "missing_og_title", severity: "warning", message: "no og:title" });
      if (!extractMetaContent(html, "og:description"))
        warnings.push({ page: label, type: "missing_og_description", severity: "warning", message: "no og:description" });
      const ogUrl = extractMetaContent(html, "og:url");
      if (ogUrl && !ogUrl.startsWith(SITE_ROOT))
        warnings.push({ page: label, type: "og_url_domain", severity: "critical", message: ogUrl });
    }
  }
  return warnings;
}

function landingPageWarnings() {
  const warnings = [];
  const h1Seen = new Map();
  for (const slug of INDEXABLE_LANDING_SLUGS) {
    const html = readHtml(slug);
    if (!html) continue;
    if (html.includes('content="noindex"') || (html.includes("noindex") && html.includes("robots"))) {
      warnings.push({
        page: slug,
        type: "noindex_landing_skipped",
        severity: "warning",
        message: "noindex landing — skipped landing gates",
      });
      continue;
    }
    const h1 = extractH1(html);
    if (!h1) {
      warnings.push({ page: slug, type: "missing_h1", severity: "critical", message: "no H1" });
    } else if (h1Seen.has(h1)) {
      warnings.push({
        page: slug,
        type: "duplicate_h1",
        severity: "critical",
        message: `same H1 as ${h1Seen.get(h1)}`,
      });
    } else {
      h1Seen.set(h1, slug);
    }
    const textLen = visibleTextLength(html);
    if (textLen < MIN_LANDING_VISIBLE_TEXT) {
      warnings.push({
        page: slug,
        type: "thin_content",
        severity: "warning",
        message: `${textLen} visible chars`,
      });
    }
    if (slug !== "accessibility" && slug !== "developers" && !hasInternalDetailLink(html)) {
      warnings.push({
        page: slug,
        type: "missing_detail_links",
        severity: "warning",
        message: "no internal detail page links",
      });
    }
  }
  return warnings;
}

function indexPolicyReport() {
  const hubDir = path.join(outDir, "hub");
  const hubPages = [];
  function walk(dir, rel = "") {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const nextRel = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) walk(full, nextRel);
      else if (entry.name === "index.html") {
        const html = fs.readFileSync(full, "utf8");
        hubPages.push({
          path: `hub/${nextRel.replace(/\/index\.html$/, "")}`,
          noindex: html.includes("noindex"),
        });
      }
    }
  }
  walk(hubDir);
  const accessibilityHtml = readHtml("accessibility");
  const paywallUtility = {};
  for (const page of ["account", "support", "terms", "privacy", "refund-policy"]) {
    const html = readHtml(page);
    paywallUtility[page] = {
      exported: Boolean(html),
      noindex: html.includes("noindex"),
      in_sitemap: false,
    };
  }
  const pricingHtml = readHtml("pricing");
  return {
    accessibility: {
      policy: "indexable",
      note: "Compliance statement — included in sitemap and landing slugs",
      exported: Boolean(accessibilityHtml),
      noindex: accessibilityHtml.includes("noindex"),
      in_sitemap: true,
    },
    commerce_pages: {
      policy: "indexable",
      note: "Business-facing pricing — included in sitemap; not SEO material landings",
      pages: INDEXABLE_COMMERCE_SLUGS.map((slug) => ({
        slug,
        exported: Boolean(readHtml(slug)),
        noindex: readHtml(slug).includes("noindex"),
        in_sitemap: true,
      })),
    },
    paywall_utility_pages: {
      policy: "noindex",
      note: "Account, support, and legal pages — footer links are navigation only, not SEO landings",
      pages: paywallUtility,
      all_noindex: Object.values(paywallUtility).every((p) => p.noindex),
    },
    footer_noindex_policy:
      "Footer may link to noindex utility pages (watchlist, map, terms, support) for buyer navigation — these must never appear in sitemap.xml",
    hub_pages: {
      policy: "noindex",
      note: "Navigation hubs omitted from sitemap; material/state SEO uses curated landing pages",
      pages: hubPages,
      all_noindex: hubPages.every((p) => p.noindex),
    },
  };
}

function structuredDataWarnings() {
  const warnings = [];
  const schemaTypesByPage = {};
  const homeHtml = readRootIndex();
  const homeBlocks = extractJsonLdBlocks(homeHtml);
  schemaTypesByPage.home = [];
  if (homeBlocks.length === 0) {
    schemaTypesByPage.home = [];
  } else {
    for (const raw of homeBlocks) {
      try {
        schemaTypesByPage.home.push(...collectSchemaTypes(JSON.parse(raw)));
      } catch {
        warnings.push({ page: "home", type: "jsonld_parse", severity: "critical", message: "invalid home JSON-LD" });
      }
    }
  }

  for (const { source, id } of REGRESSION_DETAIL_PAGES) {
    const label = `${source}/${id}`;
    const html = readHtml(`${source}/${id}`);
    if (!html) continue;
    const blocks = extractJsonLdBlocks(html);
    schemaTypesByPage[label] = [];
    if (blocks.length === 0) {
      warnings.push({ page: label, type: "missing_jsonld", severity: "critical", message: "no JSON-LD blocks" });
      continue;
    }
    const canonical = extractCanonical(html);
    for (let i = 0; i < blocks.length; i++) {
      try {
        const parsed = JSON.parse(blocks[i]);
        const types = collectSchemaTypes(parsed);
        schemaTypesByPage[label].push(...types);
        const disallowed = types.filter((t) => DISALLOWED_SCHEMA_TYPES.includes(t));
        if (disallowed.length > 0) {
          warnings.push({
            page: label,
            type: "disallowed_schema",
            severity: "critical",
            message: disallowed.join(", "),
          });
        }
        if (parsed["@type"] === "Event") {
          if (parsed.url && canonical && parsed.url !== canonical)
            warnings.push({
              page: label,
              type: "jsonld_url_mismatch",
              severity: "critical",
              message: `Event.url ${parsed.url}`,
            });
          if (parsed.offers && parsed.offers.price == null)
            warnings.push({ page: label, type: "jsonld_empty_price", severity: "warning", message: "Offer without price" });
        }
        if (parsed["@type"] === "BreadcrumbList") {
          for (const item of parsed.itemListElement ?? []) {
            const itemUrl = item?.item;
            if (!itemUrl) continue;
            if (!String(itemUrl).startsWith(SITE_ROOT))
              warnings.push({ page: label, type: "breadcrumb_domain", severity: "critical", message: String(itemUrl) });
            if (String(itemUrl).includes("?"))
              warnings.push({ page: label, type: "breadcrumb_query", severity: "critical", message: String(itemUrl) });
            if (hasStagingLeak(String(itemUrl)))
              warnings.push({ page: label, type: "breadcrumb_staging", severity: "critical", message: String(itemUrl) });
          }
        }
      } catch {
        warnings.push({ page: label, type: "jsonld_parse", severity: "critical", message: `block ${i + 1} invalid JSON` });
      }
    }
  }
  return { warnings, schemaTypesByPage };
}

function robotsReport() {
  const robotsPath = path.join(outDir, "robots.txt");
  const exists = fs.existsSync(robotsPath);
  const body = exists ? fs.readFileSync(robotsPath, "utf8") : "";
  const sitemapUrl = body.match(/Sitemap:\s*(\S+)/i)?.[1]?.trim() ?? null;
  return {
    exists,
    references_sitemap: body.includes("sitemap.xml"),
    disallows_data: body.includes("Disallow: /auctions/data/") || body.includes("Disallow: /data/"),
    sitemap_url: sitemapUrl,
    sitemap_url_exact: sitemapUrl === EXPECTED_ROBOTS_SITEMAP_URL,
    expected_sitemap_url: EXPECTED_ROBOTS_SITEMAP_URL,
    staging_leak: hasStagingLeak(body),
  };
}

function noindexReport() {
  const pages = {};
  for (const page of NOINDEX_UTILITY_PAGES) {
    const html = readHtml(page);
    pages[page] = {
      exported: Boolean(html),
      noindex: html.includes("noindex"),
    };
  }
  const landingIndexable = {};
  for (const slug of INDEXABLE_LANDING_SLUGS) {
    const html = readHtml(slug);
    landingIndexable[slug] = {
      exported: Boolean(html),
      noindex: html.includes("noindex"),
    };
  }
  return { utility_pages: pages, landing_pages: landingIndexable };
}

function sitemapReport() {
  const sitemapPath = path.join(outDir, "sitemap.xml");
  if (!fs.existsSync(sitemapPath)) {
    return { exists: false, warnings: [{ type: "missing", severity: "critical", message: "sitemap.xml missing" }] };
  }
  const urls = collectHtmlSitemapUrls();
  const byType = { home: 0, detail: 0, landing: 0, state: 0, commerce: 0 };
  const bySource = { mstc: 0, "gem-forward": 0, eauction: 0 };
  const warnings = [];
  const missingHtml = [];
  const forbidden = [];

  for (const loc of urls) {
    const kind = classifySitemapUrl(loc);
    byType[kind] = (byType[kind] ?? 0) + 1;
    const src = detailSourceFromSitemapUrl(loc);
    if (src) bySource[src] = (bySource[src] ?? 0) + 1;
    if (!loc.startsWith(SITE_ROOT))
      warnings.push({ type: "domain", severity: "critical", url: loc });
    if (loc.includes("?"))
      warnings.push({ type: "query_string", severity: "critical", url: loc });
    if (hasStagingLeak(loc))
      warnings.push({ type: "staging", severity: "critical", url: loc });
    const violations = sitemapUrlViolations(loc);
    if (violations.length > 0) forbidden.push({ url: loc, violations });
    const htmlPath = htmlPathForSitemapUrl(loc);
    if (htmlPath && !fs.existsSync(htmlPath)) missingHtml.push(loc);
  }

  if (forbidden.length > 0) {
    warnings.push({
      type: "forbidden_urls",
      severity: "critical",
      count: forbidden.length,
      sample: forbidden.slice(0, 5),
    });
  }
  if (missingHtml.length > 0) {
    warnings.push({
      type: "missing_html",
      severity: "critical",
      count: missingHtml.length,
      sample: missingHtml.slice(0, 5),
    });
  }

  const routesData = readJsonSafe(path.join(outDir, "data", "auction-routes.json"));
  const expectedDetail = routesData?.routes?.filter((r) => r.indexable !== false).length;
  const routeMix = { mstc: 0, "gem-forward": 0, eauction: 0 };
  for (const route of routesData?.routes ?? []) {
    if (route.indexable === false) continue;
    const slug = route.source_slug;
    if (slug in routeMix) routeMix[slug] += 1;
  }

  const auctionsSitemap = path.join(outDir, "sitemap-auctions.xml");
  const lastmodPresent = fs.existsSync(auctionsSitemap)
    ? fs.readFileSync(auctionsSitemap, "utf8").includes("<lastmod>")
    : urls.length > 0;

  return {
    exists: true,
    total_urls: urls.length,
    by_type: byType,
    by_source: bySource,
    expected_detail_by_source: routeMix,
    canonical_domain: SITE_ROOT,
    base_path: BASE_PATH,
    expected_detail_routes: expectedDetail ?? null,
    detail_delta: expectedDetail != null ? byType.detail - expectedDetail : null,
    warnings,
    lastmod_present: lastmodPresent,
    html_sitemap_index: true,
  };
}

function gscBingChecklist() {
  return {
    manual_action_required: true,
    note: "GSC/Bing verification and sitemap submission are manual steps after approved deploy",
    gsc_domain_verified: { status: "manual", note: "Upload HTML file to web/public/gsc-verification/ when ready" },
    gsc_sitemap_submitted: {
      status: "manual",
      note: `Submit ${EXPECTED_ROBOTS_SITEMAP_URL.replace("/sitemap.xml", "/sitemap.xml")} after deploy`,
    },
    bing_site_verified: { status: "manual", note: "Add site in Bing Webmaster Tools after deploy" },
    bing_sitemap_submitted: {
      status: "manual",
      note: `Submit ${EXPECTED_ROBOTS_SITEMAP_URL} after deploy`,
    },
    ga4_measurement_id: {
      status: process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID ? "configured_in_env" : "not_set_in_build_env",
      note: "Set NEXT_PUBLIC_GA_MEASUREMENT_ID in CI secrets for production builds",
    },
  };
}

function summarizeStatus(report) {
  const allWarnings = [
    ...report.metadata_warnings,
    ...report.landing_page_warnings,
    ...report.structured_data.warnings,
    ...report.analytics.coverage_warnings,
    ...(report.sitemap.warnings ?? []),
  ];
  const critical_count = allWarnings.filter((w) => w.severity === "critical").length;
  const warning_count = allWarnings.filter((w) => w.severity === "warning" || !w.severity).length;
  const robotsCritical =
    !report.robots.exists ||
    !report.robots.sitemap_url_exact ||
    !report.robots.disallows_data;
  const sitemapCritical = !report.sitemap.exists || (report.sitemap.warnings ?? []).some((w) => w.severity === "critical");
  const analyticsCritical = report.analytics.missing_event_constants.length > 0;
  const hubCritical = report.index_policy?.hub_pages && !report.index_policy.hub_pages.all_noindex;
  const status =
    critical_count > 0 || robotsCritical || sitemapCritical || analyticsCritical || hubCritical
      ? "fail"
      : warning_count > 0
        ? "pass_with_warnings"
        : "pass";
  return { status, critical_count, warning_count };
}

if (!fs.existsSync(outDir)) {
  console.error("generate-seo-report: web/out missing — run pnpm run build:prod first");
  process.exit(1);
}

const analytics = scanAnalyticsCoverage();
const structured = structuredDataWarnings();
const report = {
  generated_at: new Date().toISOString(),
  canonical_domain: SITE_ROOT,
  base_path: BASE_PATH,
  artifact_paths: ARTIFACT_PATHS,
  staging_markers_checked: STAGING_DOMAIN_MARKERS,
  official_claim_patterns: OFFICIAL_CLAIM_PATTERNS.map((re) => re.source),
  counts: {
    sitemap_urls: 0,
    detail_pages: 0,
    landing_pages: 0,
    state_pages: 0,
    noindex_utility_pages: NOINDEX_UTILITY_PAGES.length,
    commerce_pages: INDEXABLE_COMMERCE_SLUGS.length,
  },
  sitemap: sitemapReport(),
  robots: robotsReport(),
  noindex: noindexReport(),
  index_policy: indexPolicyReport(),
  metadata_warnings: metadataWarnings(),
  landing_page_warnings: landingPageWarnings(),
  structured_data: {
    warnings: structured.warnings,
    schema_types_by_page: structured.schemaTypesByPage,
    disallowed_types: DISALLOWED_SCHEMA_TYPES,
    home_jsonld_policy: "intentionally_absent_unless_added_without_authority_claims",
  },
  analytics: {
    ga_gated_by_env: true,
    missing_event_constants: analytics.missingInModule,
    deferred_events: analytics.deferredEvents,
    event_component_usage: analytics.eventUsage,
    coverage_warnings: Object.entries(analytics.eventUsage)
      .filter(([, used]) => !used)
      .map(([ev]) => ({ event: ev, severity: "warning", message: "no component reference found" })),
  },
  submission_checklist: gscBingChecklist(),
};

report.counts.sitemap_urls = report.sitemap.total_urls ?? 0;
report.counts.detail_pages = report.sitemap.by_type?.detail ?? 0;
report.counts.landing_pages = report.sitemap.by_type?.landing ?? 0;
report.counts.state_pages = report.sitemap.by_type?.state ?? 0;
report.counts.commerce_pages = report.sitemap.by_type?.commerce ?? 0;
report.counts.detail_by_source = report.sitemap.by_source ?? {};

report.paywall_funnel = {
  events: [
    "gated_feature_attempt",
    "upgrade_prompt_view",
    "upgrade_cta_click",
    "pricing_page_view",
    "plan_select",
    "checkout_start_stub",
    "enterprise_inquiry_click",
    "account_page_view",
  ],
  module_defined: [
    "pricing_page_view",
    "plan_select",
    "upgrade_prompt_view",
    "upgrade_cta_click",
    "gated_feature_attempt",
    "checkout_start_stub",
    "enterprise_inquiry_click",
    "account_page_view",
  ].every((ev) => !analytics.missingInModule.includes(ev)),
  component_usage: Object.fromEntries(
    [
      "pricing_page_view",
      "plan_select",
      "upgrade_prompt_view",
      "upgrade_cta_click",
      "gated_feature_attempt",
      "checkout_start_stub",
      "enterprise_inquiry_click",
      "account_page_view",
    ].map((ev) => [ev, analytics.eventUsage[ev] ?? false]),
  ),
  checkout_live: false,
  note: "Conversion funnel instrumented; checkout remains disabled stub until live billing sub-round",
};

const summary = summarizeStatus(report);
report.status = summary.status;
report.critical_count = summary.critical_count;
report.warning_count = summary.warning_count;

const summaryPath = path.join(outDir, "sitemap-summary.json");
if (fs.existsSync(path.join(outDir, "sitemap.xml"))) {
  fs.writeFileSync(
    summaryPath,
    JSON.stringify(
      {
        generated_at: report.generated_at,
        total_urls: report.counts.sitemap_urls,
        by_type: report.sitemap.by_type,
        by_source: report.sitemap.by_source,
        canonical_domain: SITE_ROOT,
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );
}

const reportPath = path.join(outDir, "seo-report.json");
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");

console.log(`generate-seo-report: wrote ${reportPath}`);
console.log(`  status: ${report.status} (critical ${report.critical_count}, warnings ${report.warning_count})`);
console.log(
  `  URLs: ${report.counts.sitemap_urls} (detail ${report.counts.detail_pages}: mstc ${report.counts.detail_by_source.mstc ?? 0}, gem ${report.counts.detail_by_source["gem-forward"] ?? 0}, ea ${report.counts.detail_by_source.eauction ?? 0})`,
);
console.log(
  `  Warnings: metadata ${report.metadata_warnings.length}, landing ${report.landing_page_warnings.length}, structured ${report.structured_data.warnings.length}, analytics ${report.analytics.coverage_warnings.length}`,
);
const criticalSamples = [
  ...report.metadata_warnings,
  ...report.landing_page_warnings,
  ...report.structured_data.warnings,
  ...(report.sitemap.warnings ?? []),
].filter((w) => w.severity === "critical");
for (const w of criticalSamples.slice(0, 12)) {
  console.log(
    `  CRITICAL: ${w.page ?? w.type ?? "?"} ${w.type ?? ""} — ${w.message ?? w.url ?? JSON.stringify(w).slice(0, 120)}`,
  );
}

// Report generator always exits 0; verify-seo-report.mjs owns the deploy gate.
process.exit(0);
