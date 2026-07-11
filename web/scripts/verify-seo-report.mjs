#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const reportPath = path.join(__dirname, "..", "out", "seo-report.json");

let ok = true;
function pass(label, cond, detail = "") {
  const mark = cond ? "OK" : "FAIL";
  if (!cond) ok = false;
  console.log(`${mark}  ${label}${detail ? ` — ${detail}` : ""}`);
}

pass("seo-report.json exists", fs.existsSync(reportPath));

if (fs.existsSync(reportPath)) {
  let report;
  try {
    report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
    pass("seo-report.json parses", true);
  } catch {
    pass("seo-report.json parses", false);
    process.exit(1);
  }
  pass("canonical_domain set", Boolean(report.canonical_domain));
  pass("status field present", Boolean(report.status));
  pass("status not fail", report.status !== "fail", report.status);
  pass("critical_count present", typeof report.critical_count === "number", String(report.critical_count));
  pass("warning_count present", typeof report.warning_count === "number", String(report.warning_count));
  pass("artifact_paths present", Boolean(report.artifact_paths?.sitemap));
  pass("counts.sitemap_urls > 0", (report.counts?.sitemap_urls ?? 0) > 0, String(report.counts?.sitemap_urls));
  pass("counts.detail_by_source present", Boolean(report.counts?.detail_by_source));
  pass("sitemap by_source present", Boolean(report.sitemap?.by_source));
  pass("submission_checklist present", Boolean(report.submission_checklist));
  pass("manual_action_required flagged", report.submission_checklist?.manual_action_required === true);
  pass("index_policy present", Boolean(report.index_policy));
  pass("hub pages all noindex", report.index_policy?.hub_pages?.all_noindex !== false);
  pass("paywall utility pages all noindex", report.index_policy?.paywall_utility_pages?.all_noindex !== false);
  pass("paywall funnel section present", Boolean(report.paywall_funnel?.events?.length));
  pass("structured_data schema policy present", Boolean(report.structured_data?.disallowed_types));
  pass(
    "metadata warnings bounded",
    (report.metadata_warnings?.length ?? 0) < 30,
    String(report.metadata_warnings?.length ?? 0),
  );
}

process.exit(ok ? 0 : 1);
