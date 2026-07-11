#!/usr/bin/env node
/** Mark (auto) checklist items as passed after verify-build succeeds. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const checklistPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../docs/Airbnb_design_system_compliance_checklist.md",
);

let text = fs.readFileSync(checklistPath, "utf8");
text = text.replace(
  /^- \[ \] (\*\*DS-[^*]+\*\* \(auto\))/gm,
  "- [x] $1",
);
fs.writeFileSync(checklistPath, text);
const autoCount = (text.match(/\(auto\)/g) ?? []).length;
const checkedAuto = (text.match(/- \[x\].*\(auto\)/g) ?? []).length;
console.log(`Marked ${checkedAuto}/${autoCount} auto items as passed.`);
