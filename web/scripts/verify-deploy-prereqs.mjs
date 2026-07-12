#!/usr/bin/env node
/**
 * Fast pre-scrape / pre-deploy gate for repo files that verify-build also checks.
 * Runs without web/out so CI fails in seconds instead of after a long scrape.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(webRoot, "..");

let failed = 0;

function check(label, ok, detail = "") {
  if (ok) {
    console.log(`OK  deploy-prereq: ${label}`);
    return;
  }
  failed += 1;
  console.error(`FAIL  deploy-prereq: ${label}${detail ? ` — ${detail}` : ""}`);
}

const envExample = path.join(repoRoot, ".env.example");
check(".env.example exists", fs.existsSync(envExample), envExample);
if (fs.existsSync(envExample)) {
  const envBody = fs.readFileSync(envExample, "utf8");
  check(
    ".env.example has NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED",
    envBody.includes("NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED"),
  );
  check(
    ".env.example has NEXT_PUBLIC_PAYWALL_DEMO_MODE",
    envBody.includes("NEXT_PUBLIC_PAYWALL_DEMO_MODE"),
  );
  check(".env.example has no live secret values", !/sk_live_|rzp_live_/.test(envBody));
  check(
    ".env.example has no NEXT_PUBLIC_*SECRET placeholders",
    !/^NEXT_PUBLIC_.*SECRET/m.test(envBody),
  );
}

const runbook = path.join(repoRoot, "docs", "PAYWALL_RUNBOOK.md");
check("docs/PAYWALL_RUNBOOK.md exists (must be committed)", fs.existsSync(runbook), runbook);
if (fs.existsSync(runbook)) {
  const body = fs.readFileSync(runbook, "utf8").toLowerCase();
  check("PAYWALL_RUNBOOK mentions billing", body.includes("billing"));
  check("PAYWALL_RUNBOOK mentions entitlements", body.includes("entitlement"));
  check(
    "PAYWALL_RUNBOOK mentions a payment provider",
    body.includes("razorpay") || body.includes("stripe"),
  );
}

const checklist = path.join(repoRoot, "docs", "RELEASE_CHECKLIST.md");
check("docs/RELEASE_CHECKLIST.md exists", fs.existsSync(checklist));
if (fs.existsSync(checklist)) {
  const body = fs.readFileSync(checklist, "utf8").toLowerCase();
  check("RELEASE_CHECKLIST mentions paywall", body.includes("paywall"));
}

if (failed > 0) {
  console.error(
    `\n${failed} deploy prerequisite(s) failed. Fix and commit these files before scrape/deploy.`,
  );
  process.exit(1);
}

console.log("\nAll deploy prerequisites OK.");
