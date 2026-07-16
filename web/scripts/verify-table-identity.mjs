/**
 * Unit checks for table-identity helpers (run: npx tsx scripts/verify-table-identity.mjs).
 * Uses dynamic import of the TS module via tsx when executed as:
 *   npx tsx --eval ... 
 * This file is a plain runner that imports the compiled path through tsx.
 */

import assert from "node:assert/strict";
import {
  buildTableIdentity,
  clampText,
  isMstcSlashPath,
  isWeakMaterialLabel,
  parseMstcAuctionPath,
  tableClampedPrimary,
} from "../src/lib/table-identity.ts";

const PATH =
  "MSTC/SRO/Paramakudi Agricultural Producers Coop Marketing Society/6/Paramakudi/26-27/19304[590088]";

assert.equal(isMstcSlashPath(PATH), true);
assert.equal(isMstcSlashPath("Ferrous scrap lot"), false);
assert.equal(isWeakMaterialLabel("Other"), true);
assert.equal(isWeakMaterialLabel("other"), true);
assert.equal(isWeakMaterialLabel("Ferrous"), false);
assert.equal(clampText("abcdefghij", 6), "abcde…");

const parsed = parseMstcAuctionPath(PATH);
assert.ok(parsed);
assert.equal(parsed.region, "SRO");
assert.equal(
  parsed.seller,
  "Paramakudi Agricultural Producers Coop Marketing Society",
);
assert.equal(parsed.city, "Paramakudi");
assert.equal(parsed.bracketId, "590088");
assert.equal(parsed.shortRef, "590088");

const identity = buildTableIdentity({
  auction_number: PATH,
  item_summary: PATH,
  display_title: "Other",
  display_material_category: "other",
  source: "mstc",
});

assert.ok(
  identity.primary.startsWith("Paramakudi Agricultural"),
  `primary should be seller, got ${identity.primary}`,
);
assert.equal(identity.secondary, "590088 · SRO");
assert.equal(identity.secondaryTooltip, PATH);
assert.equal(identity.tertiary, null, "Other grade must be hidden");
assert.ok(!identity.primary.includes("MSTC/"), "primary must not be slash path");
assert.ok(
  !`${identity.primary}\n${identity.secondary}\n${identity.tertiary}`.includes(
    "Other · MSTC",
  ),
);

const good = buildTableIdentity({
  auction_number: "MSTC-12345",
  display_title: "12.5 MT Ferrous scrap",
  display_material_category: "ferrous_scrap",
  source: "mstc",
});
assert.equal(good.primary, "12.5 MT Ferrous scrap");
assert.equal(good.tertiary, "Ferrous scrap");

const clamped = tableClampedPrimary("A".repeat(40), 20);
assert.equal(clamped.display.length, 20);
assert.ok(clamped.title?.length === 40);

console.log("OK verify-table-identity");
