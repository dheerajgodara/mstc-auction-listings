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

/** Public UI must not expose bulk CSV/watchlist export (Forge 006 / Anvil Phase 001). */
const PUBLIC_EXPORT_FORBIDDEN = [
  { label: "export-csv import", pattern: /@\/lib\/export-csv/ },
  { label: "csv_export analytics", pattern: /csv_export/ },
  { label: "Export CSV copy", pattern: /Export CSV/i },
  { label: "watchlist calendar export", pattern: /Export calendar/i },
  { label: "onExport prop", pattern: /\bonExport\b/ },
];

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

function scanPublicExportControls() {
  const srcRoots = [
    path.join(webRoot, "src", "components"),
    path.join(webRoot, "src", "app"),
  ];
  const hits = [];
  for (const root of srcRoots) {
    for (const file of collectSourceFiles(root)) {
      const rel = path.relative(webRoot, file);
      const body = fs.readFileSync(file, "utf8");
      for (const rule of PUBLIC_EXPORT_FORBIDDEN) {
        if (rule.pattern.test(body)) {
          hits.push(`${rel}: ${rule.label}`);
        }
      }
    }
  }
  return hits;
}

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

const exportHits = scanPublicExportControls();
ok(
  "public export controls absent in web/src",
  exportHits.length === 0,
  exportHits.length ? exportHits.slice(0, 5).join("; ") : "",
);

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
  ok("robots.txt exists", fs.existsSync(path.join(outDir, "robots.txt")));
  ok(
    "index.html has canonical link",
    indexHtml.includes('rel="canonical"') || indexHtml.includes("canonical"),
  );
  ok(
    "index.html has Open Graph tags",
    indexHtml.includes("og:title") || indexHtml.includes('property="og:title"'),
  );
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

const jsonPath = path.join(outDir, "data", "auctions.json");
let localPdfLinkCount = 0;
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

  const regressionIds = ["582972", "584985", "588051"];
  for (const rid of regressionIds) {
    const found = (data.auctions || []).find((a) => String(a.id) === rid);
    if (!found) {
      warn(`regression auction ${rid}`, "skipped (not in current export)");
      continue;
    }
    ok(
      `regression auction ${rid} has imported_at`,
      Boolean(found.imported_at || found.first_seen_at),
    );
  }

  const badPdf = (data.auctions || []).filter(
    (a) => a.pdf_url && a.pdf_url.startsWith("/pdfs/"),
  );
  ok(
    "no absolute /pdfs/ links in JSON",
    badPdf.length === 0,
    badPdf.length ? `${badPdf.length} still absolute` : "all relative or base-path safe",
  );

  const missingPdfRefs = (data.auctions || []).filter((a) => {
    if (!a.pdf_url || !String(a.pdf_url).startsWith("pdfs/")) return false;
    localPdfLinkCount += 1;
    return !fs.existsSync(path.join(outDir, a.pdf_url));
  });
  ok(
    "all relative auction PDF links exist in output",
    missingPdfRefs.length === 0,
    missingPdfRefs.length
      ? missingPdfRefs.slice(0, 10).map((a) => `${a.id}:${a.pdf_url}`).join(", ")
      : "",
  );

  const missingDocRefs = [];
  const missingThumbRefs = [];
  for (const auction of data.auctions || []) {
    for (const url of auction.document_urls || []) {
      const rel = String(url || "").replace(/^\//, "");
      if (rel.startsWith("docs/") || rel.startsWith("pdfs/")) {
        if (rel.startsWith("pdfs/")) localPdfLinkCount += 1;
        if (!fs.existsSync(path.join(outDir, rel))) {
          missingDocRefs.push(`${auction.id}:${rel}`);
        }
      }
    }
    for (const lot of auction.lots || []) {
      for (const img of lot.preview_images || []) {
        const url =
          typeof img === "string"
            ? img
            : img?.url || img?.thumbnail_url || img?.src || "";
        const rel = String(url || "").replace(/^\//, "");
        if (!rel.startsWith("thumbs/") && !rel.startsWith("docs/")) continue;
        if (!fs.existsSync(path.join(outDir, rel))) {
          missingThumbRefs.push(`${auction.id}:${rel}`);
        }
      }
    }
  }
  ok(
    "all relative docs/pdf document links exist in output",
    missingDocRefs.length === 0,
    missingDocRefs.slice(0, 10).join(", "),
  );
  ok(
    "all relative thumbs links exist in output",
    missingThumbRefs.length === 0,
    missingThumbRefs.slice(0, 10).join(", "),
  );

  const serialized = JSON.stringify(data);
  ok("no absolute /docs/ links in JSON", !serialized.includes('"/docs/'));
  ok("no absolute /thumbs/ links in JSON", !serialized.includes('"/thumbs/'));
}

ok(
  "pdfs/ directory has PDFs or export has no local PDF links",
  pdfCount > 0 || localPdfLinkCount === 0,
  `${pdfCount} files, ${localPdfLinkCount} local PDF links`,
);

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

const htaccessPath = path.join(outDir, ".htaccess");
if (fs.existsSync(htaccessPath)) {
  const htaccess = fs.readFileSync(htaccessPath, "utf8");
  ok(
    "htaccess disables cache for auction data files",
    htaccess.includes("no-store") && htaccess.includes("auctions-data"),
  );
}

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
  ["-m", "pytest", "tests/test_deploy_safety.py", "tests/test_display_enrichment.py", "tests/test_import_tracking.py", "tests/test_ai_enrichment.py", "-q"],
  { cwd: repoRoot, encoding: "utf8" },
);
ok(
  "display/deploy python tests",
  pyTests.status === 0,
  pyTests.status === 0 ? "" : (pyTests.stdout || pyTests.stderr || "").trim().slice(-200),
);

const aiDisplayCheck = spawnSync("node", ["scripts/verify-ai-display.mjs"], {
  cwd: webRoot,
  encoding: "utf8",
});
ok(
  "AI display fallback verification",
  aiDisplayCheck.status === 0,
  aiDisplayCheck.status === 0 ? "" : (aiDisplayCheck.stdout || aiDisplayCheck.stderr || "").trim(),
);

const failed = checks.filter((c) => !c.pass);
process.exit(failed.length ? 1 : 0);
