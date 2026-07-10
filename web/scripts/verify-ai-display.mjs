#!/usr/bin/env node
/**
 * Offline verification for AI display fallback rules (display-enrichment.ts contract).
 */
import assert from "node:assert/strict";

function isAiReady(auction) {
  return auction.ai_status === "ready" && Boolean(auction.ai_clean_heading);
}

function isAiConfidenceUsable(confidence) {
  return confidence === "high" || confidence === "medium";
}

function resolveDisplayTitle(auction) {
  if (
    isAiReady(auction) &&
    isAiConfidenceUsable(auction.ai_confidence) &&
    auction.ai_clean_heading
  ) {
    return auction.ai_clean_heading;
  }
  return auction.display_title ?? auction.item_summary ?? "—";
}

function resolveDisplayBuyerSummary(auction) {
  if (
    isAiReady(auction) &&
    isAiConfidenceUsable(auction.ai_confidence) &&
    auction.ai_buyer_summary
  ) {
    return auction.ai_buyer_summary;
  }
  return auction.display_buyer_summary ?? null;
}

const baseAuction = {
  id: "582972",
  item_summary: "Tower Parts; Earthwire",
  display_title: "459 MT Transmission Scrap",
  display_buyer_summary: "Floor ₹1,00,000 · 2 lots",
};

const readyAuction = {
  ...baseAuction,
  ai_status: "ready",
  ai_confidence: "high",
  ai_clean_heading: "AI Clean Heading",
  ai_buyer_summary: "AI buyer summary without commercial facts.",
};

const rejectedAuction = {
  ...baseAuction,
  ai_status: "rejected",
  ai_confidence: "high",
  ai_clean_heading: "Rejected Heading",
  ai_buyer_summary: "Should not show",
};

const lowConfidenceAuction = {
  ...readyAuction,
  ai_confidence: "low",
};

const missingAiMode = process.argv.includes("--missing-ai");

if (missingAiMode) {
  const noAi = { ...baseAuction };
  delete noAi.ai_status;
  assert.equal(resolveDisplayTitle(noAi), baseAuction.display_title);
  assert.equal(resolveDisplayBuyerSummary(noAi), baseAuction.display_buyer_summary);
  console.log("OK  site tolerates missing AI fields");
  process.exit(0);
}

assert.equal(resolveDisplayTitle(readyAuction), "AI Clean Heading");
assert.equal(
  resolveDisplayBuyerSummary(readyAuction),
  "AI buyer summary without commercial facts.",
);
assert.equal(resolveDisplayTitle(rejectedAuction), baseAuction.display_title);
assert.equal(resolveDisplayBuyerSummary(rejectedAuction), baseAuction.display_buyer_summary);
assert.equal(resolveDisplayTitle(lowConfidenceAuction), baseAuction.display_title);
assert.equal(resolveDisplayBuyerSummary(lowConfidenceAuction), baseAuction.display_buyer_summary);

console.log("OK  AI display prefers ready validated fields with rule-based fallback");
