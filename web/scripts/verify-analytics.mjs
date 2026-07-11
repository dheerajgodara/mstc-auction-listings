#!/usr/bin/env node
/** GA4 analytics module and event taxonomy verification. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const analyticsPath = path.join(webRoot, "src", "lib", "analytics.ts");

const REQUIRED_EVENTS = [
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
  "diligence_open",
  "compare_add",
  "compare_remove",
  "map_view",
  "map_select",
  "command_palette",
  "status_page_view",
  "saved_search_save",
  "pricing_page_view",
  "plan_select",
  "upgrade_prompt_view",
  "upgrade_cta_click",
  "gated_feature_attempt",
  "checkout_start_stub",
  "enterprise_inquiry_click",
  "account_page_view",
  "launch_readiness_page_view",
];

const DEFERRED_EVENTS = [];

const EVENT_HELPERS = {
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
  pricing_page_view: ["trackPricingPageView"],
  plan_select: ["trackPlanSelect"],
  upgrade_prompt_view: ["trackUpgradePromptView"],
  upgrade_cta_click: ["trackUpgradeCtaClick"],
  gated_feature_attempt: ["trackGatedFeatureAttempt"],
  checkout_start_stub: ["trackCheckoutStartStub"],
  enterprise_inquiry_click: ["trackEnterpriseInquiryClick"],
  account_page_view: ["trackAccountPageView"],
  launch_readiness_page_view: ["trackLaunchReadinessPageView"],
};

const COMPONENT_EVENT_MAP = [
  { file: "auction-listings-app.tsx", events: ["page_view"] },
  { file: "auction-detail-analytics.tsx", events: ["view_auction_detail"] },
  { file: "seo-landing-page.tsx", events: ["view_landing"] },
  {
    file: "auction-discovery-view.tsx",
    events: ["search", "no_results", "compare_add", "compare_remove", "diligence_open"],
  },
  { file: "discovery-toolbar.tsx", events: ["sort_change"] },
  { file: "auction-card.tsx", events: ["watchlist_toggle", "pdf_open", "source_open"] },
  { file: "lot-details.tsx", events: ["lot_expand"] },
  { file: "command-palette.tsx", events: ["apply_saved_search", "command_palette"] },
  { file: "map-page-app.tsx", events: ["map_view"] },
  { file: "map-view-client.tsx", events: ["map_select"] },
  { file: "status-page-app.tsx", events: ["status_page_view"] },
  { file: "pricing-page-app.tsx", events: ["pricing_page_view", "plan_select", "checkout_start_stub", "enterprise_inquiry_click"] },
  { file: "account-page-app.tsx", events: ["account_page_view"] },
  { file: "upgrade-prompt.tsx", events: ["upgrade_prompt_view", "upgrade_cta_click", "gated_feature_attempt", "checkout_start_stub", "enterprise_inquiry_click"] },
  { file: "use-auction-discovery.ts", events: ["filter_change", "saved_search_save"] },
  { file: "support-page-app.tsx", events: ["enterprise_inquiry_click"] },
  { file: "launch-readiness-page-app.tsx", events: ["launch_readiness_page_view"] },
];

const MAX_PARAM_STRING_LENGTH = 200;
const FORBIDDEN_PARAM_KEYS = [
  "description",
  "document_text",
  "notes",
  "full_query",
  "lot_description",
  "raw_text",
];

function usesEvent(body, event) {
  if (body.includes(`"${event}"`) || body.includes(`'${event}'`)) return true;
  for (const helper of EVENT_HELPERS[event] ?? []) {
    if (body.includes(helper)) return true;
  }
  return false;
}

function scanTrackEventPayloads(src) {
  const issues = [];
  const re = /trackEvent\s*\(\s*["'`]([^"'`]+)["'`]\s*,\s*\{([^}]*)\}/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    const eventName = m[1];
    const body = m[2];
    for (const key of FORBIDDEN_PARAM_KEYS) {
      if (new RegExp(`\\b${key}\\s*:`).test(body)) {
        issues.push({ event: eventName, issue: `forbidden param key: ${key}` });
      }
    }
    const stringLiterals = body.match(/:\s*["'`]([^"'`]{201,})["'`]/g);
    if (stringLiterals?.length) {
      issues.push({ event: eventName, issue: "string literal exceeds 200 chars" });
    }
    if (/\[[\s\S]*\]/.test(body)) {
      issues.push({ event: eventName, issue: "array literal in event params" });
    }
  }
  return issues;
}

const src = fs.readFileSync(analyticsPath, "utf8");
let failed = 0;

function check(label, pass) {
  console.log(`${pass ? "OK" : "FAIL"}  analytics: ${label}`);
  if (!pass) failed++;
}

function note(label) {
  console.log(`NOTE analytics: ${label}`);
}

check("NEXT_PUBLIC_GA_MEASUREMENT_ID gate", src.includes("NEXT_PUBLIC_GA_MEASUREMENT_ID"));
check("trackEvent helper", src.includes("export function trackEvent"));
check("trackPageView helper", src.includes("export function trackPageView"));
check("gtag guard", src.includes("window.gtag"));
check("undefined param sanitization", src.includes("v !== undefined"));
check("ANALYTICS_EVENTS constant", src.includes("ANALYTICS_EVENTS"));
check("search term truncated", src.includes(".slice(0, 100)"));
check("map city truncated", src.includes(".slice(0, 80)"));

for (const ev of REQUIRED_EVENTS) {
  check(`event constant: ${ev}`, src.includes(`"${ev}"`));
}

for (const { event, reason } of DEFERRED_EVENTS) {
  check(`deferred event constant: ${event}`, src.includes(`"${event}"`));
  note(`${event} deferred — ${reason}`);
}

const componentDir = path.join(webRoot, "src", "components");
const hooksDir = path.join(webRoot, "src", "hooks");
const allSources = [];
function walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(tsx|ts)$/.test(entry.name)) allSources.push(fs.readFileSync(full, "utf8"));
  }
}
walk(componentDir);
walk(hooksDir);
allSources.push(src);

const payloadIssues = allSources.flatMap((body) => scanTrackEventPayloads(body));
check("low-cardinality payload guard", payloadIssues.length === 0, payloadIssues.slice(0, 3).map((i) => `${i.event}: ${i.issue}`).join("; "));

for (const { file, events } of COMPONENT_EVENT_MAP) {
  const filePath = path.join(webRoot, "src", "components", file);
  const hookPath = path.join(webRoot, "src", "hooks", file);
  const resolved = fs.existsSync(filePath) ? filePath : hookPath;
  if (!fs.existsSync(resolved)) {
    check(`component exists: ${file}`, false);
    continue;
  }
  const body = fs.readFileSync(resolved, "utf8");
  for (const ev of events) {
    check(`${file} uses ${ev}`, usesEvent(body, ev));
  }
}

process.exit(failed ? 1 : 0);
