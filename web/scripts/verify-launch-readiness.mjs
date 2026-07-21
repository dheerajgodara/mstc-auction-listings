#!/usr/bin/env node
/** Launch readiness verification (Anvil Phase 006). */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FORBIDDEN_SITEMAP_UTILITY_PATHS,
  readHtml,
  collectHtmlSitemapUrls,
} from "./seo-lib.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");
const repoRoot = path.resolve(webRoot, "..");

const LAUNCH_DESIGN_BANNED = [
  /text-emerald-/,
  /dark:text-emerald/,
  /bg-emerald-/,
  /text-amber-/,
  /bg-amber-/,
  /border-amber-/,
  /text-sky-/,
  /bg-sky-/,
  /border-sky-/,
  /text-red-\d/,
  /bg-red-\d/,
  /border-red-\d/,
];

const LAUNCH_STAGES = ["internal", "soft_launch", "paid_beta", "public_launch"];

let failed = 0;

function check(label, pass, detail = "") {
  console.log(`${pass ? "OK" : "FAIL"}  launch: ${label}${detail ? ` — ${detail}` : ""}`);
  if (!pass) failed++;
}

function hasNoindex(html) {
  return html.includes('content="noindex"') || (html.includes("noindex") && html.includes("robots"));
}

function scanLaunchDesignSafety(files) {
  const hits = [];
  for (const rel of files) {
    const full = path.join(webRoot, rel);
    if (!fs.existsSync(full)) continue;
    const text = fs.readFileSync(full, "utf8");
    for (const re of LAUNCH_DESIGN_BANNED) {
      if (re.test(text)) {
        hits.push(`${rel}: ${re.source}`);
      }
    }
  }
  return hits;
}

if (!fs.existsSync(outDir)) {
  console.error("out/ not found — run pnpm run build:prod first");
  process.exit(1);
}

const reportPath = path.join(outDir, "launch-readiness.json");
const dataReportPath = path.join(outDir, "data", "launch-readiness.json");
const mdPath = path.join(outDir, "launch-readiness.md");

check("launch-readiness.json exists", fs.existsSync(reportPath));
check("data/launch-readiness.json exists", fs.existsSync(dataReportPath));
check("launch-readiness.md exists", fs.existsSync(mdPath));

let report = null;
if (fs.existsSync(reportPath)) {
  try {
    report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
  } catch {
    check("launch-readiness.json parses", false);
  }
}

if (report) {
  check("report phase is 006", report.phase === "006");
  check("launch_approved is false", report.launch_approved === false);
  check(
    "current_stage_recommendation valid",
    LAUNCH_STAGES.includes(report.current_stage_recommendation),
    report.current_stage_recommendation ?? "missing",
  );
  check("readiness_score is number", typeof report.readiness_score === "number");
  check(
    "groups present",
    Array.isArray(report.groups) && report.groups.length >= 8,
    `${report.groups?.length ?? 0} groups`,
  );
  check("hard_blockers is array", Array.isArray(report.hard_blockers));
  check("warnings is array", Array.isArray(report.warnings));
  check("manual_gates is array", Array.isArray(report.manual_gates));
  check(
    "next_steps is array",
    Array.isArray(report.next_steps) && report.next_steps.length > 0,
  );
  check("source_counts present", Boolean(report.source_counts?.mstc != null));
  check("freshness block present", Boolean(report.freshness?.threshold_hours));
  for (const group of report.groups ?? []) {
    check(
      `group ${group.id} has gates`,
      Array.isArray(group.gates) && group.gates.length > 0,
      group.id,
    );
  }
  const manualApproval = report.groups
    ?.flatMap((g) => g.gates)
    .some((g) => g.id === "launch_approval_manual" && g.manual && g.blocker);
  check("launch approval gate is manual blocker", Boolean(manualApproval));
  const billingGate = report.groups
    ?.flatMap((g) => g.gates)
    .find((g) => g.id === "checkout_disabled");
  check("checkout gate passes", billingGate?.status === "pass", billingGate?.status ?? "missing");
}

if (fs.existsSync(mdPath)) {
  const md = fs.readFileSync(mdPath, "utf8");
  check("markdown includes recommended stage", /Recommended stage:/i.test(md));
  check("markdown launch approved false", /Launch approved:\s*\*\*no\*\*/i.test(md));
  check("markdown includes source counts", /Source counts:/i.test(md) && /MSTC/i.test(md));
  check("markdown includes manual gates section", /## Manual gates/i.test(md));
  check("markdown includes next steps", /## Next steps/i.test(md));
  check(
    "markdown clarifies manual gate semantics",
    /paid beta|public launch/i.test(md) && /soft launch/i.test(md),
  );
}

const launchHtml = readHtml("launch-readiness");
check("launch-readiness page exported", launchHtml.length > 0);
check("launch-readiness page noindex", hasNoindex(launchHtml));

const sitemapPath = path.join(outDir, "sitemap.xml");
if (fs.existsSync(sitemapPath)) {
  const urls = collectHtmlSitemapUrls();
  check(
    "sitemap excludes /launch-readiness/",
    !urls.some((u) => u.includes("/launch-readiness/")),
  );
  for (const segment of FORBIDDEN_SITEMAP_UTILITY_PATHS) {
    const normalized = segment.replace(/^\//, "").replace(/\/$/, "");
    const leaked = urls.filter((u) => u.includes(`/${normalized}/`) || u.endsWith(`/${normalized}`));
    check(
      `sitemap excludes ${segment}`,
      leaked.length === 0,
      leaked.length ? leaked.slice(0, 2).join("; ") : "",
    );
  }
}

const launchLibPath = path.join(webRoot, "src", "lib", "launch-readiness.ts");
const launchAppPath = path.join(webRoot, "src", "components", "launch-readiness-page-app.tsx");
const designHits = scanLaunchDesignSafety([
  "src/lib/launch-readiness.ts",
  "src/components/launch-readiness-page-app.tsx",
]);
check(
  "launch readiness sources use Airbnb tokens only",
  designHits.length === 0,
  designHits.slice(0, 4).join("; "),
);

const analyticsSrc = fs.readFileSync(path.join(webRoot, "src", "lib", "analytics.ts"), "utf8");
check("analytics defines launch_readiness_page_view", analyticsSrc.includes("launch_readiness_page_view"));

const pageSrc = fs.readFileSync(launchAppPath, "utf8");
check("launch page uses canonical readiness tracker", pageSrc.includes("trackLaunchReadinessPageView"));
check(
  "launch page avoids duplicate launch_readiness_page_view trackEvent",
  !pageSrc.includes('trackEvent("launch_readiness_page_view")'),
);

const footerSrc = fs.readFileSync(path.join(webRoot, "src", "components", "site-footer.tsx"), "utf8");
check(
  "footer omits launch-readiness buyer link",
  !footerSrc.includes('href: "launch-readiness/"'),
);

const statusSrc = fs.readFileSync(path.join(webRoot, "src", "components", "status-page-app.tsx"), "utf8");
check(
  "status page links launch readiness in ops context",
  statusSrc.includes("launch-readiness") && /Operations|ops/i.test(statusSrc),
);

const reportIssueSrc = fs.readFileSync(
  path.join(webRoot, "src", "components", "report-issue-form.tsx"),
  "utf8",
);
const supportHtml = readHtml("support");
check(
  "support or report issue feedback path exists",
  reportIssueSrc.includes("Report") || supportHtml.includes("report") || supportHtml.includes("support@"),
);

const launchLibSrc = fs.readFileSync(launchLibPath, "utf8");
check(
  "launch lib hardcodes launch_approved false type",
  launchLibSrc.includes("launch_approved: false"),
);
check(
  "launch page states billing blocked for paid/public",
  pageSrc.includes("live billing") || pageSrc.includes("paid beta"),
);

const requiredDocs = [
  "docs/LAUNCH_RUNBOOK.md",
  "docs/SOFT_LAUNCH_PLAYBOOK.md",
  "docs/BUYER_FEEDBACK_SOP.md",
  "docs/LAUNCH_OUTREACH_TEMPLATES.md",
  "docs/LAUNCH_REPORT_TEMPLATE.md",
];
for (const doc of requiredDocs) {
  check(`${doc} exists`, fs.existsSync(path.join(repoRoot, doc)));
}

const outreach = fs.readFileSync(path.join(repoRoot, "docs/LAUNCH_OUTREACH_TEMPLATES.md"), "utf8");
check(
  "outreach templates docs-only safety wording",
  /docs only|do not auto-send|do not automate/i.test(outreach),
);

const pkg = fs.readFileSync(path.join(webRoot, "package.json"), "utf8");
check("verify-build includes verify-launch-readiness", pkg.includes("verify-launch-readiness"));

process.exit(failed ? 1 : 0);
