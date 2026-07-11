import type { Metadata } from "next";
import { buildMaterialLanding } from "@/lib/seo/material-landings";
const landing = buildMaterialLanding(
  "/coal-auctions/",
  "Coal Auctions India | Government Coal & Fuel Lots",
  "Government coal auction listings with quantity, location, and closing schedules.",
  "Coal auctions from CIL subsidiaries, power utilities, and PSUs list ROM coal, washed coal, and fuel stock disposals. Browse active coal-related auctions with MT quantities and delivery locations.\n\nVerify GCV, moisture, and delivery terms in official auction notices.",
  (a) => a.asset_category === "coal" || a.display_material_category === "coal",
);
export const metadata: Metadata = landing.metadata;
export default function CoalAuctionsLandingPage() {
  return landing.page;
}
