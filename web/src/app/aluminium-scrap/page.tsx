import type { Metadata } from "next";
import { buildMaterialLanding } from "@/lib/seo/material-landings";
const landing = buildMaterialLanding(
  "/aluminium-scrap/",
  "Aluminium Scrap Auctions India",
  "Government aluminium scrap and conductor auctions with lot details and closing dates.",
  "Aluminium scrap and conductor auctions from power utilities and PSUs often list large MT quantities. This page filters active aluminium-related auctions with parsed quantity summaries and locations.\n\nVerify alloy grades and contamination limits in official auction documents.",
  (a) => a.display_material_category === "aluminium_conductor",
);
export const metadata: Metadata = landing.metadata;
export default function AluminiumScrapLandingPage() {
  return landing.page;
}
