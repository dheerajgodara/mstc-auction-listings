import type { AuctionRecord } from "@/types/auction";

export type CommodityClass =
  | "ferrous"
  | "non_ferrous"
  | "ewaste"
  | "machinery"
  | "vehicle"
  | "coal"
  | "timber"
  | "other";

function inferCommodityClass(auction: AuctionRecord): CommodityClass {
  const mat = (auction.display_material_category ?? "").toLowerCase();
  const cat = auction.asset_category ?? "other";
  if (cat === "ewaste" || mat.includes("e-waste") || mat.includes("ewaste"))
    return "ewaste";
  if (cat === "machinery" || mat.includes("machinery") || mat.includes("plant"))
    return "machinery";
  if (cat === "vehicle") return "vehicle";
  if (cat === "coal" || mat.includes("coal")) return "coal";
  if (cat === "timber") return "timber";
  if (
    mat.includes("copper") ||
    mat.includes("alumin") ||
    mat.includes("brass") ||
    mat.includes("non-ferrous") ||
    mat.includes("conductor")
  ) {
    return "non_ferrous";
  }
  if (
    cat === "scrap" ||
    mat.includes("ferrous") ||
    mat.includes("steel") ||
    mat.includes("hms") ||
    mat.includes("melting")
  ) {
    return "ferrous";
  }
  return "other";
}

export function commodityBorderClass(_auction?: AuctionRecord): string {
  const commodity = _auction ? inferCommodityClass(_auction) : "other";
  switch (commodity) {
    case "non_ferrous":
      return "border-l-4 border-l-[#ff385c]";
    case "ferrous":
      return "border-l-4 border-l-[#717171]";
    case "vehicle":
      return "border-l-4 border-l-[#00a699]";
    case "coal":
      return "border-l-4 border-l-[#222222]";
    case "timber":
      return "border-l-4 border-l-[#fc642d]";
    case "machinery":
      return "border-l-4 border-l-[#b0b0b0]";
    case "ewaste":
      return "border-l-4 border-l-[#914669]";
    default:
      return "border-l-4 border-l-border";
  }
}

export function commodityClassLabel(auction: AuctionRecord): CommodityClass {
  return inferCommodityClass(auction);
}
