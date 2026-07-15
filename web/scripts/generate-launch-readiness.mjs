#!/usr/bin/env node
/**
 * Generate launch-readiness.json and launch-readiness.md (Anvil Phase 006).
 * Evaluates gates from built artifacts and repo source files.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  BASE_PATH,
  EXPECTED_ROBOTS_SITEMAP_URL,
  FORBIDDEN_SITEMAP_UTILITY_PATHS,
  SITE_ROOT,
  STAGING_DOMAIN_MARKERS,
  hasStagingLeak,
  readHtml,
  readRootIndex,
  resolveRegressionDetailPages,
  sitemapUrlsFromXml,
} from "./seo-lib.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");
const repoRoot = path.resolve(webRoot, "..");
const publicDataDir = path.join(webRoot, "public", "data");

const FRESHNESS_THRESHOLD_HOURS = 36;
const MIN_AUCTION_COUNT = 1000;
const CAPPED_MSTC_MAX = 500;

const PAYMENT_SDK_PACKAGES = [
  "@stripe/stripe-js",
  "@stripe/react-stripe-js",
  "stripe",
  "razorpay",
  "@razorpay/checkout",
];

const REQUIRED_ANALYTICS_EVENTS = [
  "page_view",
  "search",
  "view_auction_detail",
  "source_open",
  "pdf_open",
  "watchlist_toggle",
  "apply_saved_search",
  "pricing_page_view",
  "checkout_start_stub",
  "status_page_view",
  "launch_readiness_page_view",
];

const REQUIRED_DOCS = [
  "docs/LAUNCH_RUNBOOK.md",
  "docs/SOFT_LAUNCH_PLAYBOOK.md",
  "docs/BUYER_FEEDBACK_SOP.md",
  "docs/LAUNCH_OUTREACH_TEMPLATES.md",
  "docs/LAUNCH_REPORT_TEMPLATE.md",
];

const groups = [];

function readRepo(rel) {
  const full = path.join(repoRoot, rel);
  return fs.existsSync(full) ? fs.readFileSync(full, "utf8") : "";
}

function readOut(rel) {
  const full = path.join(outDir, rel);
  return fs.existsSync(full) ? fs.readFileSync(full, "utf8") : "";
}

function readJsonOut(rel) {
  const full = path.join(outDir, rel);
  if (!fs.existsSync(full)) return null;
  try {
    return JSON.parse(fs.readFileSync(full, "utf8"));
  } catch {
    return null;
  }
}

function gate(id, title, status, detail = "", opts = {}) {
  return {
    id,
    title,
    status,
    detail: detail || undefined,
    manual: Boolean(opts.manual),
    blocker: Boolean(opts.blocker),
  };
}

function addGroup(id, title, gates) {
  groups.push({ id, title, gates });
}

function parseAgeHours(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.round((ms / 3_600_000) * 10) / 10;
}

function sourceCountsFromExport(data) {
  const counts = { mstc: 0, gem_forward: 0, eauction: 0 };
  for (const a of data?.auctions ?? []) {
    const src = String(a.source ?? "").toLowerCase();
    if (src in counts) counts[src] += 1;
    else if (src === "gem-forward") counts.gem_forward += 1;
  }
  if (data?.stats?.by_source) {
    for (const [k, v] of Object.entries(data.stats.by_source)) {
      const key = k === "gem-forward" ? "gem_forward" : k;
      if (key in counts && typeof v === "number") counts[key] = v;
    }
  }
  return counts;
}

function evaluateDataGates(exportData, routesData) {
  const auctions = exportData?.auctions ?? [];
  const total = exportData?.count ?? auctions.length;
  const sourceCounts = sourceCountsFromExport(exportData);
  const sourcesPresent = Object.entries(sourceCounts)
    .filter(([, n]) => n > 0)
    .map(([k]) => k);
  const missingImport = auctions.filter((a) => !(a.imported_at || a.first_seen_at)).length;
  const ageHours = parseAgeHours(exportData?.automation_ran_at);
  const withinFreshness =
    ageHours == null ? undefined : ageHours <= FRESHNESS_THRESHOLD_HOURS;
  const preferredRegressionIds = ["582972", "584985", "588051"];
  const missingRegression = preferredRegressionIds.filter(
    (id) => !auctions.some((a) => String(a.id) === id),
  );
  const routeCount = routesData?.routes?.length ?? 0;
  const isCappedMstcOnly =
    total <= CAPPED_MSTC_MAX &&
    sourcesPresent.length === 1 &&
    sourcesPresent[0] === "mstc";

  addGroup("data", "Data & sources", [
    gate(
      "auction_count_min",
      `At least ${MIN_AUCTION_COUNT} auctions`,
      total >= MIN_AUCTION_COUNT ? "pass" : "fail",
      `${total} auctions`,
      { blocker: total < MIN_AUCTION_COUNT },
    ),
    gate(
      "source_mstc",
      "MSTC source present",
      sourceCounts.mstc > 0 ? "pass" : "fail",
      `${sourceCounts.mstc} auctions`,
      { blocker: sourceCounts.mstc === 0 },
    ),
    gate(
      "source_gem_forward",
      "GeM Forward source present",
      sourceCounts.gem_forward > 0 ? "pass" : "fail",
      `${sourceCounts.gem_forward} auctions`,
      { blocker: sourceCounts.gem_forward === 0 },
    ),
    gate(
      "source_eauction",
      "eAuction source present",
      sourceCounts.eauction > 0 ? "pass" : "fail",
      `${sourceCounts.eauction} auctions`,
      { blocker: sourceCounts.eauction === 0 },
    ),
    gate(
      "no_capped_mstc_only",
      "No capped MSTC-only export",
      isCappedMstcOnly ? "fail" : "pass",
      isCappedMstcOnly ? `${total} MSTC-only` : "multi-source export",
      { blocker: isCappedMstcOnly },
    ),
    gate(
      "import_timestamps",
      "Import timestamps on auctions",
      missingImport === 0 ? "pass" : "fail",
      missingImport ? `${missingImport} missing` : "all present",
      { blocker: missingImport > 0 },
    ),
    gate(
      "automation_timestamp",
      "automation_ran_at present",
      exportData?.automation_ran_at ? "pass" : "fail",
      exportData?.automation_ran_at ?? "missing",
      { blocker: !exportData?.automation_ran_at },
    ),
    gate(
      "freshness_threshold",
      `Freshness within ${FRESHNESS_THRESHOLD_HOURS}h`,
      withinFreshness === undefined
        ? "warn"
        : withinFreshness
          ? "pass"
          : "warn",
      ageHours == null
        ? "cannot compute age"
        : `${ageHours}h since automation_ran_at`,
    ),
    gate(
      "regression_auctions",
      "Regression auction IDs present",
      missingRegression.length === 0 ? "pass" : "warn",
      missingRegression.length
        ? `missing: ${missingRegression.join(", ")}`
        : regressionIds.join(", "),
    ),
    gate(
      "detail_route_count",
      "Detail routes match auction count",
      routeCount === 0
        ? "warn"
        : Math.abs(routeCount - total) <= Math.max(5, total * 0.01)
          ? "pass"
          : "warn",
      `routes ${routeCount}, auctions ${total}`,
    ),
  ]);

  return { total, sourceCounts, ageHours, withinFreshness };
}

function evaluateScraperGates() {
  const refreshWf = readRepo(".github/workflows/refresh-and-deploy.yml");
  const legacyWf = readRepo(".github/workflows/scrape-and-deploy.yml");
  const legacyScheduled =
    legacyWf.includes("schedule:") &&
    !legacyWf.includes("# schedule:") &&
    /schedule:\s*\n/.test(legacyWf);
  const safetyGates = readRepo("scraper/safety_gates.py");
  const deployPy = readRepo("scraper/deploy.py");
  const rollbackDoc =
    readRepo("docs/RELEASE_CHECKLIST.md").includes("Rollback") ||
    readRepo("docs/PRODUCTION_STATUS.md").includes("Recovery");
  const statusReport = fs.existsSync(path.join(repoRoot, "scraper/status_report.py"));
  const httpVerify = fs.existsSync(path.join(repoRoot, "scraper/http_verify.py"));
  const freshnessCheck = fs.existsSync(path.join(repoRoot, "scraper/freshness_check.py"));
  const freshnessWf = readRepo(".github/workflows/freshness-check.yml");
  const legacyUnsafe =
    legacyWf.includes('sources: ["mstc"]') ||
    legacyWf.includes("sources=mstc") ||
    legacyWf.includes("limit=300");

  addGroup("scraper", "Scraper & automation", [
    gate(
      "production_refresh_workflow",
      "Production refresh workflow exists",
      refreshWf.includes("refresh_and_deploy") ? "pass" : "fail",
      ".github/workflows/refresh-and-deploy.yml",
      { blocker: !refreshWf.includes("refresh_and_deploy") },
    ),
    gate(
      "legacy_not_scheduled",
      "Legacy diagnostic workflow not scheduled",
      legacyScheduled ? "fail" : "pass",
      legacyScheduled ? "schedule block active" : "dispatch only",
      { blocker: legacyScheduled },
    ),
    gate(
      "safety_gates",
      "Safety gates module exists",
      safetyGates.includes("def ") || safetyGates.includes("class ") ? "pass" : "fail",
      "scraper/safety_gates.py",
    ),
    gate(
      "deploy_safety",
      "Deploy export safety check",
      deployPy.includes("validate_deploy_export") ? "pass" : "fail",
      "scraper/deploy.py",
    ),
    gate(
      "rollback_docs",
      "Rollback documentation",
      rollbackDoc ? "pass" : "warn",
      "RELEASE_CHECKLIST / PRODUCTION_STATUS",
    ),
    gate(
      "status_report_cli",
      "Status report CLI",
      statusReport ? "pass" : "warn",
      "scraper/status_report.py",
    ),
    gate(
      "http_verify",
      "HTTP verification script",
      httpVerify ? "pass" : "fail",
      "scraper/http_verify.py",
    ),
    gate(
      "freshness_check",
      "Freshness check script",
      freshnessCheck ? "pass" : "fail",
      "scraper/freshness_check.py",
    ),
    gate(
      "monitoring_workflow",
      "Scheduled freshness workflow",
      freshnessWf.includes("freshness") ? "pass" : "warn",
      ".github/workflows/freshness-check.yml",
    ),
    gate(
      "no_unsafe_legacy_defaults",
      "Legacy workflow unsafe defaults documented",
      legacyUnsafe ? "warn" : "pass",
      legacyUnsafe ? "capped MSTC defaults present — manual only" : "guarded",
    ),
  ]);
}

function evaluateSeoGates() {
  const sitemapXml = readOut("sitemap.xml");
  const robotsTxt = readOut("robots.txt");
  const seoReport = readJsonOut("seo-report.json");
  const urls = sitemapXml ? sitemapUrlsFromXml(sitemapXml) : [];
  const detailUrls = urls.filter((u) => /\/(mstc|gem-forward|eauction)\/[^/]+\/$/.test(u));
  const hasPricing = urls.some((u) => u.includes("/pricing/"));
  const forbiddenUtility = urls.filter((u) =>
    FORBIDDEN_SITEMAP_UTILITY_PATHS.some((seg) => u.includes(seg.replace(/\//g, "/"))),
  );
  const hasLaunchReadinessInSitemap = urls.some((u) => u.includes("/launch-readiness/"));
  const homeHtml = readRootIndex();
  const canonical = homeHtml.match(/rel=["']canonical["'][^>]+href=["']([^"']+)["']/i)?.[1] ?? "";
  const stagingLeak =
    hasStagingLeak(sitemapXml) ||
    hasStagingLeak(homeHtml) ||
    STAGING_DOMAIN_MARKERS.some((m) => canonical.toLowerCase().includes(m));

  addGroup("seo", "SEO", [
    gate("sitemap_exists", "Sitemap generated", sitemapXml ? "pass" : "fail", "sitemap.xml", {
      blocker: !sitemapXml,
    }),
    gate(
      "sitemap_production_domain",
      "Sitemap uses production domain",
      sitemapXml && urls.every((u) => u.startsWith(SITE_ROOT)) ? "pass" : "warn",
      SITE_ROOT,
    ),
    gate(
      "sitemap_detail_pages",
      "Sitemap includes detail pages",
      detailUrls.length > 0 ? "pass" : "fail",
      `${detailUrls.length} detail URLs`,
      { blocker: detailUrls.length === 0 },
    ),
    gate(
      "sitemap_pricing",
      "Sitemap includes pricing page",
      hasPricing ? "pass" : "warn",
      hasPricing ? "/pricing/" : "missing",
    ),
    gate(
      "sitemap_noindex_excluded",
      "Noindex utility pages excluded from sitemap",
      forbiddenUtility.length === 0 && !hasLaunchReadinessInSitemap ? "pass" : "fail",
      forbiddenUtility.length
        ? forbiddenUtility.slice(0, 3).join("; ")
        : "utility pages omitted",
      { blocker: forbiddenUtility.length > 0 || hasLaunchReadinessInSitemap },
    ),
    gate(
      "robots_sitemap",
      "robots.txt references sitemap",
      robotsTxt.includes("sitemap") ? "pass" : "warn",
      EXPECTED_ROBOTS_SITEMAP_URL,
    ),
    gate(
      "canonical_production",
      "Canonical URLs use production domain",
      canonical.includes("scrapauctionindia.com") ? "pass" : "warn",
      canonical || "not found on home",
    ),
    gate(
      "seo_report_status",
      "SEO report status",
      !seoReport
        ? "warn"
        : seoReport.overall_status === "pass"
          ? "pass"
          : "warn",
      seoReport?.overall_status ?? "seo-report.json not generated yet",
    ),
    gate(
      "no_staging_leaks",
      "No staging domain leaks in metadata",
      stagingLeak ? "fail" : "pass",
      stagingLeak ? "staging marker found" : "clean",
      { blocker: stagingLeak },
    ),
  ]);
}

function evaluateAnalyticsGates() {
  const analyticsSrc = readRepo("web/src/lib/analytics.ts");
  const missingEvents = REQUIRED_ANALYTICS_EVENTS.filter((e) => !analyticsSrc.includes(`"${e}"`));
  const gaGated = analyticsSrc.includes("NEXT_PUBLIC_GA_MEASUREMENT_ID");
  const launchPageSrc = readRepo("web/src/components/launch-readiness-page-app.tsx");
  const usesLaunchEvent =
    launchPageSrc.includes("launch_readiness_page_view") ||
    launchPageSrc.includes("trackLaunchReadinessPageView");

  addGroup("analytics", "Analytics & funnel", [
    gate(
      "analytics_module",
      "Analytics helper module",
      analyticsSrc.includes("trackEvent") ? "pass" : "fail",
      "web/src/lib/analytics.ts",
    ),
    gate(
      "required_events",
      "Core funnel events defined",
      missingEvents.length === 0 ? "pass" : "warn",
      missingEvents.length ? `missing: ${missingEvents.join(", ")}` : "present",
    ),
    gate(
      "launch_readiness_event",
      "Launch readiness page view event",
      analyticsSrc.includes("launch_readiness_page_view") && usesLaunchEvent
        ? "pass"
        : "warn",
      "launch_readiness_page_view",
    ),
    gate(
      "ga_env_gated",
      "GA measurement ID env-gated",
      gaGated ? "pass" : "fail",
      "NEXT_PUBLIC_GA_MEASUREMENT_ID",
    ),
  ]);
}

function evaluatePaywallGates() {
  const pricingHtml = readHtml("pricing");
  const plansSrc = readRepo("web/src/lib/plans.ts");
  const entSrc = readRepo("web/src/lib/entitlements.ts");
  const checkoutSrc = readRepo("web/src/lib/checkout.ts");
  const packageJson = readRepo("web/package.json");
  const sdkHit = PAYMENT_SDK_PACKAGES.some((pkg) => packageJson.includes(`"${pkg}"`));
  const billingBlocked =
    checkoutSrc.includes("not_implemented") ||
    checkoutSrc.includes('reason: "disabled"');
  const utilityPages = ["account", "support", "terms", "privacy", "refund-policy"];
  const missingUtility = utilityPages.filter((p) => !fs.existsSync(path.join(outDir, p, "index.html")));

  addGroup("paywall", "Paywall & revenue", [
    gate(
      "pricing_page",
      "Pricing page exported",
      pricingHtml ? "pass" : "fail",
      "/pricing/",
      { blocker: !pricingHtml },
    ),
    gate(
      "plan_catalog",
      "Plan catalog defined",
      plansSrc.includes("PLAN_CATALOG") ? "pass" : "fail",
      "web/src/lib/plans.ts",
    ),
    gate(
      "entitlement_model",
      "Entitlement model defined",
      entSrc.includes("ENTITLEMENTS") ? "pass" : "fail",
      "web/src/lib/entitlements.ts",
    ),
    gate(
      "checkout_disabled",
      "Checkout remains disabled by default",
      billingBlocked ? "pass" : "fail",
      "startCheckoutStub returns not_implemented/disabled",
      { blocker: !billingBlocked },
    ),
    gate(
      "no_payment_sdk",
      "No payment SDK in dependencies",
      sdkHit ? "fail" : "pass",
      sdkHit ? "payment SDK found" : "clean",
      { blocker: sdkHit },
    ),
    gate(
      "account_support_legal",
      "Account, support, and legal pages exported",
      missingUtility.length === 0 ? "pass" : "warn",
      missingUtility.length ? `missing: ${missingUtility.join(", ")}` : "present",
    ),
    gate(
      "live_billing_blocked",
      "Live billing marked blocked",
      readRepo("docs/PAYWALL_RUNBOOK.md").toLowerCase().includes("disabled")
        ? "pass"
        : "warn",
      "docs/PAYWALL_RUNBOOK.md",
    ),
    gate(
      "buyer_validation_manual",
      "Buyer validation before paid launch",
      "manual",
      "Owner approval required — see RELEASE_CHECKLIST",
      { manual: true, blocker: true },
    ),
  ]);
}

function evaluateLegalGates() {
  const disclaimerSrc = readRepo("web/src/components/site-disclaimer.tsx");
  const termsHtml = readHtml("terms");
  const privacyHtml = readHtml("privacy");
  const refundHtml = readHtml("refund-policy");
  const supportHtml = readHtml("support");
  const reportIssue = readRepo("web/src/components/report-issue-form.tsx");
  const officialDisclaimer =
    disclaimerSrc.toLowerCase().includes("official") ||
    disclaimerSrc.toLowerCase().includes("mstc") ||
    disclaimerSrc.toLowerCase().includes("source");
  const govtClaim =
    readRootIndex().match(/official government|government portal|this is the official/i) != null;

  addGroup("legal", "Legal, trust & support", [
    gate(
      "site_disclaimer",
      "Site disclaimer component",
      disclaimerSrc ? "pass" : "fail",
      "site-disclaimer.tsx",
    ),
    gate(
      "terms_page",
      "Terms page",
      termsHtml ? "pass" : "fail",
      "/terms/",
    ),
    gate(
      "privacy_page",
      "Privacy page",
      privacyHtml ? "pass" : "fail",
      "/privacy/",
    ),
    gate(
      "refund_policy",
      "Refund policy page",
      refundHtml ? "pass" : "fail",
      "/refund-policy/",
    ),
    gate(
      "support_path",
      "Support page",
      supportHtml ? "pass" : "fail",
      "/support/",
    ),
    gate(
      "feedback_path",
      "Report issue / feedback path",
      reportIssue.includes("Report") || supportHtml.includes("report")
        ? "pass"
        : "warn",
      "report-issue-form or support",
    ),
    gate(
      "official_source_disclaimer",
      "Official-source disclaimer",
      officialDisclaimer ? "pass" : "warn",
      "site-disclaimer references sources",
    ),
    gate(
      "no_government_affiliation",
      "No false government affiliation claim",
      govtClaim ? "fail" : "pass",
      govtClaim ? "claim detected on home" : "clean",
      { blocker: govtClaim },
    ),
    gate(
      "legal_review_manual",
      "Legal review before paid launch",
      "manual",
      "Counsel review required — see PAYWALL_RUNBOOK",
      { manual: true, blocker: true },
    ),
  ]);
}

function evaluateOpsGates() {
  const missingDocs = REQUIRED_DOCS.filter((d) => !fs.existsSync(path.join(repoRoot, d)));
  const verifyLaunch = fs.existsSync(path.join(webRoot, "scripts/verify-launch-readiness.mjs"));
  const launchPage = fs.existsSync(path.join(outDir, "launch-readiness", "index.html"));
  const launchHtml = launchPage ? readHtml("launch-readiness") : "";
  const launchNoindex =
    launchHtml.includes("noindex") ||
    readRepo("web/src/app/launch-readiness/page.tsx").includes("NOINDEX_METADATA");
  const verifyBuild = readRepo("web/package.json").includes("verify-launch-readiness");
  const publicExportScan = readRepo("web/scripts/verify-build.mjs").includes("PUBLIC_EXPORT_FORBIDDEN");

  const regressionPages = resolveRegressionDetailPages(2);
  if (!regressionPages.length) {
    addGroup("ux", "UX & detail pages", [
      gate(
        "detail_sample_missing",
        "Detail page sample",
        "warn",
        "no detail pages in current build",
      ),
    ]);
  }
  if (!groups.some((g) => g.id === "ux")) {
    const sample = regressionPages[0];
    const html = readHtml(`${sample.source}/${sample.id}`);
    addGroup("ux", "UX & detail pages", [
      gate(
        "auction_detail_sample",
        "Sample auction detail page exported",
        html ? "pass" : "warn",
        `${sample.source}/${sample.id}`,
      ),
      gate(
        "airbnb_design_verifier",
        "Airbnb design verifier in build chain",
        readRepo("web/package.json").includes("verify-airbnb-design") ? "pass" : "warn",
        "verify-airbnb-design.mjs",
      ),
      gate(
        "no_public_export",
        "No public bulk export controls",
        publicExportScan ? "pass" : "warn",
        "verify-build export scan",
      ),
      gate(
        "soft_launch_playbook",
        "Soft launch playbook documented",
        missingDocs.includes("docs/SOFT_LAUNCH_PLAYBOOK.md") ? "warn" : "pass",
        "docs/SOFT_LAUNCH_PLAYBOOK.md",
      ),
      gate(
        "buyer_feedback_sop",
        "Buyer feedback SOP documented",
        missingDocs.includes("docs/BUYER_FEEDBACK_SOP.md") ? "warn" : "pass",
        "docs/BUYER_FEEDBACK_SOP.md",
      ),
      gate(
        "launch_report_template",
        "Launch report template documented",
        missingDocs.includes("docs/LAUNCH_REPORT_TEMPLATE.md") ? "warn" : "pass",
        "docs/LAUNCH_REPORT_TEMPLATE.md",
      ),
    ]);
  }

  addGroup("ops", "Launch ops & docs", [
    gate(
      "launch_runbook",
      "Launch runbook documented",
      missingDocs.includes("docs/LAUNCH_RUNBOOK.md") ? "fail" : "pass",
      "docs/LAUNCH_RUNBOOK.md",
      { blocker: missingDocs.includes("docs/LAUNCH_RUNBOOK.md") },
    ),
    gate(
      "launch_readiness_page",
      "Launch readiness page exported",
      launchPage ? "pass" : "warn",
      "/launch-readiness/",
    ),
    gate(
      "launch_page_noindex",
      "Launch readiness page is noindex",
      launchNoindex ? "pass" : "fail",
      "NOINDEX_METADATA",
      { blocker: !launchNoindex },
    ),
    gate(
      "launch_verifier",
      "Launch readiness verifier script",
      verifyLaunch ? "pass" : "fail",
      "verify-launch-readiness.mjs",
    ),
    gate(
      "verify_build_chain",
      "Verifier wired into verify-build",
      verifyBuild ? "pass" : "warn",
      "package.json verify-build",
    ),
    gate(
      "launch_approval_manual",
      "Public launch approval",
      "manual",
      "Owner must explicitly approve — never automatic",
      { manual: true, blocker: true },
    ),
    gate(
      "provider_gate_manual",
      "Payment provider decision",
      "manual",
      "Document provider in PAYWALL_RUNBOOK before paid launch",
      { manual: true, blocker: true },
    ),
  ]);
}

function deriveStageRecommendation(allGates) {
  const blockers = allGates.filter(
    (g) => (g.status === "fail" || g.status === "blocked") && g.blocker,
  );
  const manualBlockers = allGates.filter((g) => g.manual && g.blocker);
  if (blockers.length > 0) return "internal";
  if (manualBlockers.length > 0) return "soft_launch";
  const warns = allGates.filter((g) => g.status === "warn").length;
  if (warns > 5) return "soft_launch";
  return "public_launch";
}

function computeScore(allGates) {
  if (!allGates.length) return 0;
  const weights = { pass: 1, warn: 0.6, manual: 0.5, fail: 0, blocked: 0 };
  const sum = allGates.reduce((acc, g) => acc + (weights[g.status] ?? 0), 0);
  return Math.round((sum / allGates.length) * 100);
}

function stageRecommendationNote(stage) {
  if (stage === "soft_launch") {
    return "Soft launch may proceed with known buyers. Paid beta and public launch remain blocked until manual legal, provider, buyer, and launch-approval gates pass.";
  }
  if (stage === "internal") {
    return "Resolve hard blockers before soft launch. Manual gates will still block paid beta and public launch.";
  }
  if (stage === "paid_beta" || stage === "public_launch") {
    return "Automated gates passed; owner must still approve billing and public launch explicitly.";
  }
  return "";
}

function buildNextSteps(hardBlockers, manualGates, warnings, stage) {
  const steps = [];
  if (hardBlockers.length) {
    steps.push(`Resolve ${hardBlockers.length} hard blocker(s) before soft launch.`);
  } else if (stage === "soft_launch") {
    steps.push("Soft launch may proceed — invite known buyers per SOFT_LAUNCH_PLAYBOOK.md.");
  }
  if (manualGates.length) {
    steps.push(
      "Manual gates block paid beta and public launch only — complete legal, provider, buyer validation, and launch approval.",
    );
  }
  if (warnings.length) {
    steps.push(`Review ${warnings.length} warning(s) — informational score only.`);
  }
  if (!steps.length) {
    steps.push("Run soft launch with known buyers per SOFT_LAUNCH_PLAYBOOK.md.");
    steps.push("Collect feedback via BUYER_FEEDBACK_SOP.md before paid beta.");
  }
  steps.push("Do not enable live billing until PAYWALL_RUNBOOK gates pass.");
  return steps;
}

function renderMarkdown(report) {
  const lines = [
    "# Launch Readiness Report",
    "",
    `Generated: ${report.generated_at}`,
    `Phase: Anvil ${report.phase}`,
    `Site: ${report.site_url}`,
    `Recommended stage: **${report.current_stage_recommendation}**`,
    `Readiness score (informational): ${report.readiness_score}%`,
    `Launch approved: **no** (manual only)`,
    "",
  ];
  const stageNote = stageRecommendationNote(report.current_stage_recommendation);
  if (stageNote) {
    lines.push(`> ${stageNote}`, "");
  }
  lines.push(
    "## Summary",
    "",
    `- Total auctions: ${report.total_auctions}`,
    `- Source counts: MSTC ${report.source_counts.mstc}, GeM Forward ${report.source_counts.gem_forward}, eAuction ${report.source_counts.eauction}`,
    `- Freshness: ${report.freshness.automation_ran_at ?? "unknown"} (${report.freshness.age_hours ?? "?"}h, threshold ${report.freshness.threshold_hours}h)`,
    "",
  );
  if (report.hard_blockers.length) {
    lines.push("## Hard blockers", "");
    for (const b of report.hard_blockers) lines.push(`- ${b}`);
    lines.push("");
  }
  if (report.manual_gates.length) {
    lines.push("## Manual gates", "");
    lines.push(
      "_Manual gates block paid beta and public launch. They do not block soft launch when hard blockers are clear._",
      "",
    );
    for (const m of report.manual_gates) lines.push(`- ${m}`);
    lines.push("");
  }
  if (report.warnings.length) {
    lines.push("## Warnings", "");
    for (const w of report.warnings) lines.push(`- ${w}`);
    lines.push("");
  }
  lines.push("## Next steps", "");
  for (const s of report.next_steps) lines.push(`- ${s}`);
  lines.push("");
  for (const group of report.groups) {
    lines.push(`## ${group.title}`, "");
    lines.push("| Gate | Status | Detail |");
    lines.push("|------|--------|--------|");
    for (const g of group.gates) {
      lines.push(`| ${g.title} | ${g.status} | ${g.detail ?? ""} |`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

if (!fs.existsSync(outDir)) {
  console.error("generate-launch-readiness: out/ not found — run build:prod first");
  process.exit(1);
}

const exportData = readJsonOut("data/auctions.json");
const routesData = readJsonOut("data/auction-routes.json");

if (!exportData) {
  console.error("generate-launch-readiness: missing data/auctions.json");
  process.exit(1);
}

const { total, sourceCounts, ageHours, withinFreshness } = evaluateDataGates(
  exportData,
  routesData,
);
evaluateScraperGates();
evaluateSeoGates();
evaluateAnalyticsGates();
evaluatePaywallGates();
evaluateLegalGates();
evaluateOpsGates();

const allGates = groups.flatMap((g) => g.gates);
const hardBlockers = allGates
  .filter((g) => (g.status === "fail" || g.status === "blocked") && g.blocker)
  .map((g) => `${g.title}: ${g.detail ?? g.status}`);
const warnings = allGates
  .filter((g) => g.status === "warn")
  .map((g) => `${g.title}: ${g.detail ?? ""}`);
const manualGates = allGates
  .filter((g) => g.manual)
  .map((g) => `${g.title}: ${g.detail ?? "manual review required"}`);

const report = {
  generated_at: new Date().toISOString(),
  phase: "006",
  site_url: `${SITE_ROOT}${BASE_PATH}/`,
  current_stage_recommendation: deriveStageRecommendation(allGates),
  launch_approved: false,
  readiness_score: computeScore(allGates),
  hard_blockers: hardBlockers,
  warnings,
  manual_gates: manualGates,
  next_steps: buildNextSteps(hardBlockers, manualGates, warnings, deriveStageRecommendation(allGates)),
  source_counts: sourceCounts,
  total_auctions: total,
  freshness: {
    automation_ran_at: exportData.automation_ran_at,
    age_hours: ageHours ?? undefined,
    threshold_hours: FRESHNESS_THRESHOLD_HOURS,
    within_threshold: withinFreshness,
  },
  groups,
};

const jsonOut = path.join(outDir, "launch-readiness.json");
const mdOut = path.join(outDir, "launch-readiness.md");
const dataOut = path.join(outDir, "data", "launch-readiness.json");

fs.mkdirSync(publicDataDir, { recursive: true });
fs.mkdirSync(path.dirname(dataOut), { recursive: true });

const jsonBody = `${JSON.stringify(report, null, 2)}\n`;
fs.writeFileSync(jsonOut, jsonBody);
fs.writeFileSync(dataOut, jsonBody);
fs.writeFileSync(path.join(publicDataDir, "launch-readiness.json"), jsonBody);
fs.writeFileSync(mdOut, renderMarkdown(report));

console.log(
  `generate-launch-readiness: score ${report.readiness_score}% stage ${report.current_stage_recommendation} blockers ${hardBlockers.length} warnings ${warnings.length}`,
);
console.log(`  wrote ${jsonOut}`);
console.log(`  wrote ${mdOut}`);
