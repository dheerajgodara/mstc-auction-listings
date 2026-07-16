/**
 * Table identity helpers — gold-standard hierarchy for dense auction rows.
 * Primary = human what; Secondary = short ref; Tertiary = useful tags only.
 */

import { materialCategoryLabel } from "@/lib/display-enrichment";
import { sourceLabel } from "@/lib/discovery-constants";
import type { AuctionRecord, AuctionSource } from "@/types/auction";

export type MstcAuctionPath = {
  raw: string;
  region: string | null;
  seller: string | null;
  city: string | null;
  bracketId: string | null;
  shortRef: string | null;
};

const WEAK_MATERIAL = new Set([
  "other",
  "other scrap",
  "unknown",
  "—",
  "-",
  "n/a",
  "na",
]);

/** True when text looks like an MSTC composite slash-path ID. */
export function isMstcSlashPath(value: string | null | undefined): boolean {
  const v = (value ?? "").trim();
  if (!v) return false;
  if (/^MSTC\//i.test(v)) return true;
  const parts = v.split("/").filter(Boolean);
  return parts.length >= 5 && /\[\d+\]/.test(v);
}

/** True when a material/grade label is useless noise for the table. */
export function isWeakMaterialLabel(label: string | null | undefined): boolean {
  if (!label) return true;
  return WEAK_MATERIAL.has(label.trim().toLowerCase());
}

export function clampText(text: string, maxChars: number): string {
  const value = text.trim();
  if (value.length <= maxChars) return value;
  if (maxChars <= 1) return "…";
  return `${value.slice(0, maxChars - 1).trimEnd()}…`;
}

export function parseMstcAuctionPath(
  raw: string | null | undefined,
): MstcAuctionPath | null {
  const value = (raw ?? "").trim();
  if (!value || !isMstcSlashPath(value)) return null;

  const parts = value.split("/").map((p) => p.trim()).filter(Boolean);
  const bracketMatch = value.match(/\[(\d{4,})\]/);
  const bracketId = bracketMatch?.[1] ?? null;

  // MSTC / REGION / SELLER / … / CITY / YY-YY / ref[id]
  const region = parts.length >= 2 ? parts[1] : null;
  const seller = parts.length >= 3 ? parts[2] : null;
  // City is usually the segment before the year (YY-YY) when present
  let city: string | null = null;
  const yearIdx = parts.findIndex((p) => /^\d{2}-\d{2}$/.test(p));
  if (yearIdx > 0) {
    city = parts[yearIdx - 1] ?? null;
  } else if (parts.length >= 5) {
    city = parts[4] ?? null;
  }

  const last = parts[parts.length - 1] ?? "";
  const numericTail = last.replace(/\[\d+\]/, "").replace(/\D+/g, "");
  const shortRef = bracketId ?? (numericTail.length >= 4 ? numericTail : null);

  return {
    raw: value,
    region: region && region.toUpperCase() !== "MSTC" ? region : null,
    seller: seller && !/^\d+$/.test(seller) ? seller : null,
    city,
    bracketId,
    shortRef,
  };
}

function looksLikeGenericOtherTitle(text: string): boolean {
  const n = text.trim().toLowerCase();
  return n === "other" || n === "other scrap" || n === "scrap";
}

function firstUsefulHumanTitle(
  auction: Pick<
    AuctionRecord,
    "display_title" | "item_summary" | "auction_number"
  >,
): string | null {
  for (const candidate of [
    auction.display_title,
    auction.item_summary,
  ]) {
    const text = (candidate ?? "").trim();
    if (!text) continue;
    if (isMstcSlashPath(text)) continue;
    if (looksLikeGenericOtherTitle(text)) continue;
    return text;
  }
  return null;
}

export type TableIdentity = {
  primary: string;
  primaryFull: string;
  secondary: string | null;
  secondaryTooltip: string | null;
  tertiary: string | null;
};

const PRIMARY_MAX = 52;

/**
 * Build Auction-column identity: human primary, short ref secondary,
 * material tertiary only when useful (never "Other · MSTC").
 */
export function buildTableIdentity(
  auction: Pick<
    AuctionRecord,
    | "display_title"
    | "item_summary"
    | "auction_number"
    | "display_material_category"
    | "asset_category"
    | "source"
  >,
): TableIdentity {
  const pathRaw =
    [auction.auction_number, auction.item_summary, auction.display_title]
      .map((v) => (v ?? "").trim())
      .find((v) => isMstcSlashPath(v)) ?? null;
  const parsed = parseMstcAuctionPath(pathRaw);

  const human = firstUsefulHumanTitle(auction);
  const sellerFromPath = parsed?.seller?.trim() || null;

  let primaryFull =
    human ??
    sellerFromPath ??
    parsed?.shortRef ??
    (auction.auction_number ?? "").trim() ??
    "Auction";
  if (!primaryFull) primaryFull = "Auction";

  // Never use full slash-path as the visible primary
  if (isMstcSlashPath(primaryFull) && sellerFromPath) {
    primaryFull = sellerFromPath;
  } else if (isMstcSlashPath(primaryFull) && parsed?.shortRef) {
    primaryFull = `Auction ${parsed.shortRef}`;
  }

  const primary = clampText(primaryFull, PRIMARY_MAX);

  let secondary: string | null = null;
  let secondaryTooltip: string | null = pathRaw;
  if (parsed?.shortRef) {
    secondary = parsed.region
      ? `${parsed.shortRef} · ${parsed.region}`
      : parsed.shortRef;
  } else {
    const number = (auction.auction_number ?? "").trim();
    if (number && number !== primaryFull && !isMstcSlashPath(number)) {
      secondary = clampText(number, 36);
      secondaryTooltip = number;
    } else if (number && isMstcSlashPath(number)) {
      // Path with no parseable id — still demote to tooltip only
      secondary = null;
      secondaryTooltip = number;
    }
  }

  // Dedup: if secondary repeats primary, drop it
  if (secondary && secondary.toLowerCase() === primary.toLowerCase()) {
    secondary = null;
  }

  const grade =
    materialCategoryLabel(auction.display_material_category) ??
    auction.asset_category ??
    null;
  const tertiary = isWeakMaterialLabel(grade) ? null : grade;

  return {
    primary,
    primaryFull,
    secondary,
    secondaryTooltip,
    tertiary,
  };
}

/** Clamp helper for Qty / Location / other primaries with full tooltip. */
export function tableClampedPrimary(
  value: string | null | undefined,
  maxChars: number,
  empty = "—",
): { display: string; title: string | undefined } {
  const full = (value ?? "").trim();
  if (!full) return { display: empty, title: undefined };
  const display = clampText(full, maxChars);
  return {
    display,
    title: display !== full ? full : undefined,
  };
}

export function tableSourceToken(
  source?: AuctionSource | string | null,
): string {
  return sourceLabel((source as AuctionSource) ?? "mstc");
}
