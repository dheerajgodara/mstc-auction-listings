#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const outDir = path.join(webRoot, "out");

const checks = [];

function ok(label, pass, detail = "") {
  checks.push({ label, pass, detail });
  const mark = pass ? "OK" : "FAIL";
  console.log(`${mark}  ${label}${detail ? ` — ${detail}` : ""}`);
}

if (!fs.existsSync(outDir)) {
  console.error("out/ directory not found. Run npm run build first.");
  process.exit(1);
}

ok("index.html exists", fs.existsSync(path.join(outDir, "index.html")));
ok(
  "data/auctions.json exists",
  fs.existsSync(path.join(outDir, "data", "auctions.json")),
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
  ok("JSON count matches auctions", data.count === data.auctions?.length);
  const badPdf = (data.auctions || []).filter(
    (a) => a.pdf_url && a.pdf_url.startsWith("/pdfs/"),
  );
  ok(
    "no absolute /pdfs/ links in JSON",
    badPdf.length === 0,
    badPdf.length ? `${badPdf.length} still absolute` : "all relative or base-path safe",
  );

  const badDocs = JSON.stringify(data).includes('"/docs/');
  const badThumbs = JSON.stringify(data).includes('"/thumbs/');
  ok("no absolute /docs/ links in JSON", !badDocs);
  ok("no absolute /thumbs/ links in JSON", !badThumbs);
}

const indexHtml = fs.readFileSync(path.join(outDir, "index.html"), "utf8");
ok(
  "index.html has no bare href=\"/pdfs/",
  !indexHtml.includes('href="/pdfs/'),
);
ok(
  "index.html has no bare src=\"/thumbs/",
  !indexHtml.includes('src="/thumbs/'),
);
ok(
  "index.html has no bare href=\"/docs/",
  !indexHtml.includes('href="/docs/'),
);

const failed = checks.filter((c) => !c.pass);
process.exit(failed.length ? 1 : 0);
