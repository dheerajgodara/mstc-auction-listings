import type { Metadata } from "next";
import { buildMaterialLanding } from "@/lib/seo/material-landings";
const landing = buildMaterialLanding(
  "/timber-auctions/",
  "Timber Auctions India | Government Forest & Wood Lots",
  "Government timber and wood auctions from forest departments and PSUs.",
  "Timber auctions cover logs, poles, firewood, and processed wood lots from forest departments and government estates. Active listings show quantity, species where available, and yard locations.\n\nVerify forest transit permits and quality specifications in official documents.",
  (a) =>
    a.asset_category === "timber" || a.display_material_category === "timber",
);
export const metadata: Metadata = landing.metadata;
export default function TimberAuctionsLandingPage() {
  return landing.page;
}
