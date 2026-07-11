#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(__dirname, "..", "out");

const REGRESSION = [
  { source: "mstc", id: "582972" },
  { source: "mstc", id: "584985" },
  { source: "mstc", id: "588051" },
];

let ok = true;
function pass(label, cond, detail = "") {
  const mark = cond ? "OK" : "FAIL";
  if (!cond) ok = false;
  console.log(`${mark}  ${label}${detail ? ` — ${detail}` : ""}`);
}

for (const { source, id } of REGRESSION) {
  const htmlPath = path.join(outDir, source, id, "index.html");
  pass(`detail page ${source}/${id} exists`, fs.existsSync(htmlPath));
  if (fs.existsSync(htmlPath)) {
    const html = fs.readFileSync(htmlPath, "utf8");
    pass(`${source}/${id} has H1`, html.includes("<h1"));
    pass(`${source}/${id} has canonical`, html.includes('rel="canonical"'));
    pass(`${source}/${id} has disclaimer`, html.includes("Bidding") || html.includes("official"));
    pass(`${source}/${id} has lot content`, html.includes("Lots") || html.includes("lot-"));
  }
}

process.exit(ok ? 0 : 1);
