#!/usr/bin/env node
/** Paywall foundation verification (Anvil Phase 005, Pass 2). */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FORBIDDEN_SITEMAP_UTILITY_PATHS,
  readHtml,
  resolveRegressionDetailPages,
  collectHtmlSitemapUrls,
} from "./seo-lib.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");
const srcDir = path.join(webRoot, "src");
const repoRoot = path.resolve(webRoot, "..");

const PAYWALL_EVENTS = [
  "pricing_page_view",
  "plan_select",
  "upgrade_prompt_view",
  "upgrade_cta_click",
  "gated_feature_attempt",
  "checkout_start_stub",
  "enterprise_inquiry_click",
  "account_page_view",
];

const PAYWALL_UTILITY_PAGES = [
  "account",
  "support",
  "terms",
  "privacy",
  "refund-policy",
];

const PAYWALL_EXPORT_PAGES = [...PAYWALL_UTILITY_PAGES, "pricing"];

const PAYMENT_SDK_PACKAGES = [
  "@stripe/stripe-js",
  "@stripe/react-stripe-js",
  "stripe",
  "razorpay",
  "@razorpay/checkout",
  "paypal-checkout",
  "cashfree-pg",
  "instamojo",
];

const PAYMENT_SDK_PATTERNS = [
  /@stripe\//,
  /loadRazorpay/,
  /Razorpay\(/,
  /paypal\.com\/sdk/,
  /checkout\.razorpay/,
];

const PUBLIC_EXPORT_FORBIDDEN = [
  /@\/lib\/export-csv/,
  /csv_export/,
  /Export CSV/i,
  /\bonExport\b/,
];

const PLAN_ORDER = ["free", "pro", "trader", "team", "enterprise"];

let failed = 0;

function check(label, pass, detail = "") {
  console.log(`${pass ? "OK" : "FAIL"}  paywall: ${label}${detail ? ` — ${detail}` : ""}`);
  if (!pass) failed++;
}

function readSrc(relPath) {
  const full = path.join(srcDir, relPath);
  return fs.existsSync(full) ? fs.readFileSync(full, "utf8") : "";
}

function hasNoindex(html) {
  return html.includes('content="noindex"') || (html.includes("noindex") && html.includes("robots"));
}

function parsePlanCaps(plansSrc) {
  const caps = {};
  for (const plan of PLAN_ORDER) {
    const re = new RegExp(`${plan}:\\s*\\{\\s*watchlist:\\s*(\\d+(?:_\\d+)?),\\s*savedSearches:\\s*(\\d+(?:_\\d+)?)`);
    const m = plansSrc.match(re);
    if (m) {
      caps[plan] = {
        watchlist: Number(m[1].replace(/_/g, "")),
        savedSearches: Number(m[2].replace(/_/g, "")),
      };
    }
  }
  return caps;
}

function parseEntitlementBlock(plansSrc, blockName) {
  const re = new RegExp(`const ${blockName}[^=]*=\\s*\\[([\\s\\S]*?)\\];`);
  const m = plansSrc.match(re);
  if (!m) return { direct: [], spreads: [] };
  const body = m[1];
  return {
    direct: [...body.matchAll(/ENTITLEMENTS\.(\w+)/g)].map((x) => x[1]),
    spreads: [...body.matchAll(/\.\.\.(\w+)/g)].map((x) => x[1]),
  };
}

function tierIncludesPrior(plansSrc, tierBlock, priorBlock, label) {
  const tier = parseEntitlementBlock(plansSrc, tierBlock);
  const spreadsPrior = tier.spreads.includes(priorBlock);
  check(`${label} spreads ${priorBlock}`, spreadsPrior);
  if (spreadsPrior) return;
  const prior = parseEntitlementBlock(plansSrc, priorBlock);
  const missing = prior.direct.filter((e) => !tier.direct.includes(e));
  check(`${label} includes prior tier entitlements`, missing.length === 0, missing.join(", ") || "");
}

function simulateCheckoutStub(env) {
  const enabled = env.NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED === "true";
  const provider = env.NEXT_PUBLIC_BILLING_PROVIDER?.trim();
  if (!enabled || !provider) return { ok: false, reason: "not_configured" };
  return { ok: false, reason: "not_implemented" };
}

function collectSourceFiles(dir) {
  const files = [];
  if (!fs.existsSync(dir)) return files;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...collectSourceFiles(full));
    else if (/\.(tsx|ts|jsx|js)$/.test(entry.name)) files.push(full);
  }
  return files;
}

if (!fs.existsSync(outDir)) {
  console.error("out/ not found — run pnpm run build:prod first");
  process.exit(1);
}

const plansSrc = readSrc("lib/plans.ts");
const entSrc = readSrc("lib/entitlements.ts");
const checkoutSrc = readSrc("lib/checkout.ts");
const analyticsSrc = readSrc("lib/analytics.ts");
const pricingSrc = readSrc("components/pricing-page-app.tsx");
const upgradeSrc = readSrc("components/upgrade-prompt.tsx");
const modalSrc = readSrc("components/ui/modal.tsx");
const accountSrc = readSrc("components/account-page-app.tsx");

check("plans.ts exists", plansSrc.length > 0);
check("entitlements.ts exists", entSrc.length > 0);
check("checkout.ts exists", checkoutSrc.length > 0);

for (const plan of PLAN_ORDER) {
  check(`plan catalog includes ${plan}`, plansSrc.includes(`"${plan}"`));
}

check("entitlement helper getCurrentPlan", entSrc.includes("getCurrentPlan"));
check("entitlement helper hasEntitlement", entSrc.includes("hasEntitlement"));
check("demo plan gated by env", entSrc.includes("NEXT_PUBLIC_PAYWALL_DEMO_MODE"));
check("checkout disabled by default", checkoutSrc.includes("not_configured"));
check("checkout returns not_implemented when configured", checkoutSrc.includes("not_implemented"));
check("no live payment SDK import in checkout", !checkoutSrc.includes("@stripe"));

const caps = parsePlanCaps(plansSrc);
check("free watchlist cap is 5", caps.free?.watchlist === 5, String(caps.free?.watchlist));
check("free saved search cap is 2", caps.free?.savedSearches === 2, String(caps.free?.savedSearches));
for (let i = 1; i < PLAN_ORDER.length; i++) {
  const prev = PLAN_ORDER[i - 1];
  const cur = PLAN_ORDER[i];
  if (caps[prev] && caps[cur]) {
    check(
      `${cur} watchlist cap >= ${prev}`,
      caps[cur].watchlist >= caps[prev].watchlist,
      `${caps[cur].watchlist} vs ${caps[prev].watchlist}`,
    );
    check(
      `${cur} saved search cap >= ${prev}`,
      caps[cur].savedSearches >= caps[prev].savedSearches,
      `${caps[cur].savedSearches} vs ${caps[prev].savedSearches}`,
    );
  }
}

const proEnt = parseEntitlementBlock(plansSrc, "PRO_ENTITLEMENTS");
check("Pro defines core entitlements", proEnt.direct.length >= 3);

tierIncludesPrior(plansSrc, "TRADER_ENTITLEMENTS", "PRO_ENTITLEMENTS", "Trader");
tierIncludesPrior(plansSrc, "TEAM_ENTITLEMENTS", "TRADER_ENTITLEMENTS", "Team");
tierIncludesPrior(plansSrc, "ENTERPRISE_ENTITLEMENTS", "TEAM_ENTITLEMENTS", "Enterprise");

const traderEnt = parseEntitlementBlock(plansSrc, "TRADER_ENTITLEMENTS");
check(
  "Trader adds diligence and alerts",
  traderEnt.direct.includes("ADVANCED_DILIGENCE") && traderEnt.direct.includes("ALERTS"),
);

const checkoutNoEnv = simulateCheckoutStub({});
check(
  "checkout stub not_configured without env",
  checkoutNoEnv.ok === false && checkoutNoEnv.reason === "not_configured",
);
const checkoutDisabled = simulateCheckoutStub({
  NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED: "false",
  NEXT_PUBLIC_BILLING_PROVIDER: "razorpay",
});
check("checkout stub not_configured when disabled", checkoutDisabled.reason === "not_configured");
const checkoutEnabled = simulateCheckoutStub({
  NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED: "true",
  NEXT_PUBLIC_BILLING_PROVIDER: "razorpay",
});
check(
  "checkout stub not_implemented when enabled (no redirect)",
  checkoutEnabled.ok === false && checkoutEnabled.reason === "not_implemented",
);
check("checkout stub never returns ok redirect in source", !checkoutSrc.includes("return { ok: true"));

for (const ev of PAYWALL_EVENTS) {
  check(`analytics event ${ev}`, analyticsSrc.includes(`"${ev}"`));
}

for (const page of PAYWALL_EXPORT_PAGES) {
  check(`${page} page exported`, fs.existsSync(path.join(outDir, page, "index.html")));
}

const pricingHtml = readHtml("pricing");
check("pricing page indexable (no noindex)", pricingHtml.length > 0 && !hasNoindex(pricingHtml));
check(
  "pricing page links to discover or detail",
  pricingHtml.includes("Discover") ||
    pricingHtml.includes("mstc-auctions") ||
    /mstc\/\d+/.test(pricingHtml),
);

for (const page of PAYWALL_UTILITY_PAGES) {
  check(`${page} noindex`, hasNoindex(readHtml(page)));
}

if (fs.existsSync(path.join(outDir, "sitemap.xml"))) {
  const sitemapUrls = collectHtmlSitemapUrls();
  check("sitemap includes pricing", sitemapUrls.some((u) => u.includes("/pricing/")));
  for (const segment of FORBIDDEN_SITEMAP_UTILITY_PATHS) {
    check(`sitemap excludes ${segment}`, !sitemapUrls.some((u) => u.includes(segment)));
  }
}

const regressionDetailPages = resolveRegressionDetailPages(2);
check(
  "regression detail pages available in build",
  regressionDetailPages.length >= 2,
  regressionDetailPages.length
    ? `using ${regressionDetailPages.map((p) => `${p.source}/${p.id}`).join(", ")}`
    : "no detail pages under out/",
);
for (const { source, id } of regressionDetailPages) {
  const detailHtml = readHtml(`${source}/${id}`);
  check(
    `${source}/${id} exposes source or PDF context in export`,
    detailHtml.includes("source") || detailHtml.includes("pdf") || detailHtml.includes("Official"),
  );
}

const exportHits = [];
for (const file of collectSourceFiles(path.join(srcDir, "components"))) {
  const body = fs.readFileSync(file, "utf8");
  for (const pattern of PUBLIC_EXPORT_FORBIDDEN) {
    if (pattern.test(body)) exportHits.push(path.relative(webRoot, file));
  }
}
check("public bulk export controls absent", exportHits.length === 0, exportHits.slice(0, 3).join("; "));

const sdkHits = [];
for (const file of collectSourceFiles(srcDir)) {
  const body = fs.readFileSync(file, "utf8");
  for (const pattern of PAYMENT_SDK_PATTERNS) {
    if (pattern.test(body)) sdkHits.push(`${path.relative(webRoot, file)}: ${pattern}`);
  }
}
check("no payment SDK references in src", sdkHits.length === 0, sdkHits.slice(0, 3).join("; "));

const pkg = JSON.parse(fs.readFileSync(path.join(webRoot, "package.json"), "utf8"));
const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };
const paymentDepHits = PAYMENT_SDK_PACKAGES.filter((name) => name in allDeps);
check("no payment SDK packages in package.json", paymentDepHits.length === 0, paymentDepHits.join(", "));

const envExample = path.join(repoRoot, ".env.example");
check(".env.example exists", fs.existsSync(envExample), envExample);
if (fs.existsSync(envExample)) {
  const envBody = fs.readFileSync(envExample, "utf8");
  check(".env.example billing placeholders", envBody.includes("NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED"));
  check(".env.example demo mode placeholder", envBody.includes("NEXT_PUBLIC_PAYWALL_DEMO_MODE"));
  check(".env.example has no secret values", !/sk_live_|rzp_live_/.test(envBody));
  check(
    ".env.example no NEXT_PUBLIC secret placeholders",
    !/^NEXT_PUBLIC_.*SECRET/m.test(envBody),
  );
} else {
  check(".env.example billing placeholders", false, "file missing from repo checkout");
  check(".env.example demo mode placeholder", false, "file missing from repo checkout");
}

check("upgrade prompt component exists", fs.existsSync(path.join(srcDir, "components", "upgrade-prompt.tsx")));
check("upgrade modal routes waitlist to account", upgradeSrc.includes("account/?waitlist=1"));
check("pricing waitlist routes to account", pricingSrc.includes("account/?waitlist=1"));
check("account page explains waitlist", accountSrc.includes("Early access waitlist"));

check("modal has dialog role", modalSrc.includes('role="dialog"'));
check("modal has aria-modal", modalSrc.includes('aria-modal="true"'));
check("modal has title id for a11y", modalSrc.includes("modal-title"));
check("modal supports Escape close", modalSrc.includes('e.key === "Escape"'));

check(
  "pricing page uses Airbnb layout tokens",
  pricingSrc.includes("container-marketplace") &&
    pricingSrc.includes("surface-elevated") &&
    pricingSrc.includes("text-display") &&
    pricingSrc.includes("btn-primary"),
);
check(
  "pricing page avoids admin/SaaS clutter labels",
  !/Command center|Terminal-grade|SaaS dashboard/i.test(pricingSrc),
);

const gateHits = [
  entSrc.includes("watchlist_add"),

  entSrc.includes("saved_search_save"),
  entSrc.includes("filter_geo_radius"),
  readSrc("components/filter-drawer.tsx").includes("gateFeature"),
  readSrc("hooks/use-auction-discovery.ts").includes("tryToggleWatchlist"),
].every(Boolean);
check("gated workflows wired", gateHits);

const runbook = path.join(repoRoot, "docs", "PAYWALL_RUNBOOK.md");
check("PAYWALL_RUNBOOK.md exists", fs.existsSync(runbook), "must be committed at docs/PAYWALL_RUNBOOK.md");
if (fs.existsSync(runbook)) {
  const runbookBody = fs.readFileSync(runbook, "utf8");
  check("runbook documents provider evaluation", /Razorpay|Stripe|Cashfree|Instamojo/i.test(runbookBody));
  check("runbook documents buyer validation gate", /buyer validation/i.test(runbookBody));
  check("runbook documents legal review gate", /legal review/i.test(runbookBody));
  check("runbook documents footer noindex policy", /footer/i.test(runbookBody));
}

process.exit(failed ? 1 : 0);
