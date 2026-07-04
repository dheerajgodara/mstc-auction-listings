#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");

const INDEX_WARN_BYTES = 500_000;
const INDEX_FAIL_BYTES = 2_000_000;

const checks = [];

function ok(label, pass, detail = "") {
  checks.push({ label, pass, detail });
  const mark = pass ? "OK" : "FAIL";
  console.log(`${mark}  ${label}${detail ? ` — ${detail}` : ""}`);
}

function warn(label, detail = "") {
  console.log(`WARN ${label}${detail ? ` — ${detail}` : ""}`);
}

if (!fs.existsSync(outDir)) {
  console.error("out/ directory not found. Run pnpm run build:prod first.");
  process.exit(1);
}

const indexPath = path.join(outDir, "index.html");
ok("index.html exists", fs.existsSync(indexPath));

if (fs.existsSync(indexPath)) {
  const indexBytes = fs.statSync(indexPath).size;
  ok("index.html size recorded", true, `${indexBytes} bytes`);
  if (indexBytes > INDEX_FAIL_BYTES) {
    ok("index.html under fail threshold", false, `>${INDEX_FAIL_BYTES} bytes`);
  } else {
    ok("index.html under fail threshold", true, `limit ${INDEX_FAIL_BYTES}`);
  }
  if (indexBytes > INDEX_WARN_BYTES) {
    warn("index.html large", `${indexBytes} bytes (warn > ${INDEX_WARN_BYTES})`);
  }
  const indexHtml = fs.readFileSync(indexPath, "utf8");
  const embeddedAuctions = indexHtml.includes('"auctions":[') || indexHtml.includes('"auctions" : [');
  ok(
    "index.html does not embed full auctions JSON",
    !embeddedAuctions,
    embeddedAuctions ? "found embedded auctions array" : "shell only",
  );
}

ok(
  "data/auctions.json exists",
  fs.existsSync(path.join(outDir, "data", "auctions.json")),
);

const dataJsPath = path.join(outDir, "data", "auctions-data.js");
ok(
  "data/auctions-data.js exists (Hostinger-safe loader)",
  fs.existsSync(dataJsPath),
);

if (fs.existsSync(dataJsPath)) {
  const jsBody = fs.readFileSync(dataJsPath, "utf8");
  ok(
    "auctions-data.js exports __AUCTIONS_EXPORT__",
    jsBody.includes("window.__AUCTIONS_EXPORT__"),
  );
  ok(
    "auctions-data.js includes automation_ran_at",
    jsBody.includes('"automation_ran_at"'),
  );
  ok(
    "auctions-data.js includes imported_at",
    jsBody.includes('"imported_at"'),
  );
}

ok(
  "data/export-meta.json exists",
  fs.existsSync(path.join(outDir, "data", "export-meta.json")),
);

const pdfDir = path.join(outDir, "pdfs");
const pdfCount = fs.existsSync(pdfDir)
  ? fs.readdirSync(pdfDir).filter((f) => f.endsWith(".pdf")).length
  : 0;
ok("pdfs/ directory has PDFs", pdfCount > 0, `${pdfCount} files`);

const jsonPath = path.join(outDir, "data", "auctions.json");
if (fs.existsSync(jsonPath)) {
  const data = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  ok("JSON has generated_at", Boolean(data.generated_at));
  ok("JSON has automation_ran_at", Boolean(data.automation_ran_at));
  ok("JSON count matches auctions", data.count === data.auctions?.length);
  const missingImport = (data.auctions || []).filter(
    (a) => !(a.imported_at || a.first_seen_at),
  ).length;
  ok(
    "every auction has imported_at or first_seen_at",
    missingImport === 0,
    missingImport ? `${missingImport} missing` : "",
  );
  const a582972 = (data.auctions || []).find((a) => String(a.id) === "582972");
  ok("auction 582972 has imported_at", Boolean(a582972?.imported_at || a582972?.first_seen_at));
  const badPdf = (data.auctions || []).filter(
    (a) => a.pdf_url && a.pdf_url.startsWith("/pdfs/"),
  );
  ok(
    "no absolute /pdfs/ links in JSON",
    badPdf.length === 0,
    badPdf.length ? `${badPdf.length} still absolute` : "all relative or base-path safe",
  );

  const serialized = JSON.stringify(data);
  ok("no absolute /docs/ links in JSON", !serialized.includes('"/docs/'));
  ok("no absolute /thumbs/ links in JSON", !serialized.includes('"/thumbs/'));
}

if (fs.existsSync(indexPath)) {
  const indexHtml = fs.readFileSync(indexPath, "utf8");
  ok("index.html has no bare href=\"/pdfs/", !indexHtml.includes('href="/pdfs/'));
  ok("index.html has no bare src=\"/thumbs/", !indexHtml.includes('src="/thumbs/'));
  ok("index.html has no bare href=\"/docs/", !indexHtml.includes('href="/docs/'));
}

ok(
  ".htaccess copied to output (JSON MIME hint)",
  fs.existsSync(path.join(outDir, ".htaccess")),
  "optional on Hostinger",
);

ok(
  "status page exported",
  fs.existsSync(path.join(outDir, "status", "index.html")),
);

const historyPath = path.join(outDir, "data", "import-history.json");
if (fs.existsSync(historyPath)) {
  try {
    const history = JSON.parse(fs.readFileSync(historyPath, "utf8"));
    ok("import-history.json parses", Array.isArray(history) && history.length > 0);
  } catch {
    ok("import-history.json parses", false);
  }
} else {
  ok("import-history.json exists", false, "run finalize_public_export");
}

const statusIndex = path.join(outDir, "status", "index.html");
if (fs.existsSync(statusIndex)) {
  const statusHtml = fs.readFileSync(statusIndex, "utf8");
  ok(
    "status page does not use misleading Updated badge label",
    !statusHtml.includes("Updated:") || statusHtml.includes("Automation ran:"),
  );
}

const repoRoot = path.resolve(webRoot, "..");
const deployCheck = spawnSync(
  "python3",
  [
    "-c",
    `import sys; sys.path.insert(0, ${JSON.stringify(repoRoot)}); from scraper.deploy import validate_deploy_export; from pathlib import Path; validate_deploy_export(Path(${JSON.stringify(outDir)})); print('deploy-export-ok')`,
  ],
  { cwd: repoRoot, encoding: "utf8" },
);
ok(
  "deploy export safety on web/out",
  deployCheck.status === 0,
  deployCheck.status === 0 ? "" : (deployCheck.stderr || deployCheck.stdout || "").trim().slice(0, 200),
);

const pyTests = spawnSync(
  "python3",
  ["-m", "pytest", "tests/test_deploy_safety.py", "tests/test_display_enrichment.py", "tests/test_import_tracking.py", "-q"],
  { cwd: repoRoot, encoding: "utf8" },
);
ok(
  "display/deploy python tests",
  pyTests.status === 0,
  pyTests.status === 0 ? "" : (pyTests.stdout || pyTests.stderr || "").trim().slice(-200),
);

const failed = checks.filter((c) => !c.pass);
process.exit(failed.length ? 1 : 0);
