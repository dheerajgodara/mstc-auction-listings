export type SupplyBadge = "PSU" | "OEM" | "Insurance" | "Government" | null;
const PSU_KEYWORDS = [
  "psu",
  "government",
  "ministry",
  "railways",
  "ntpc",
  "bhel",
  "iocl",
  "ongc",
  "gail",
  "bsnl",
];
const OEM_KEYWORDS = [
  "tata",
  "mahindra",
  "maruti",
  "hyundai",
  "ashok leyland",
  "bajaj",
  "hero",
];
const INSURANCE_KEYWORDS = ["insurance", "salvage", "total loss", "irda"];
export function deriveSupplyBadge(auction: {
  seller?: string | null;
  source?: string | null;
  item_summary?: string | null;
}): SupplyBadge {
  const text =
    `${auction.seller ?? ""} ${auction.item_summary ?? ""}`.toLowerCase();
  if (INSURANCE_KEYWORDS.some((k) => text.includes(k))) return "Insurance";
  if (OEM_KEYWORDS.some((k) => text.includes(k))) return "OEM";
  if (PSU_KEYWORDS.some((k) => text.includes(k))) return "PSU";
  if (auction.source === "mstc" || auction.source === "eauction")
    return "Government";
  return null;
}
export function supplyBadgeLabel(badge: SupplyBadge): string | null {
  if (!badge) return null;
  const labels: Record<NonNullable<SupplyBadge>, string> = {
    PSU: "PSU / Government surplus",
    OEM: "Tier-1 OEM",
    Insurance: "Insurance salvage",
    Government: "Government surplus",
  };
  return labels[badge];
}
