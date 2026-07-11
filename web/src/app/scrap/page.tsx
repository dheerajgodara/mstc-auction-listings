import type { Metadata } from "next";
import { buildMaterialLanding } from "@/lib/seo/material-landings";
const landing = buildMaterialLanding(
  "/scrap/",
  "Scrap Auctions India | Government Metal & Industrial Scrap",
  "Live government scrap auctions from MSTC, GeM, and eAuction — ferrous, non-ferrous, cable, and industrial scrap.",
  "Government scrap auctions are a major channel for recyclers and metal traders to source ferrous scrap, cable, transformers, and industrial surplus. This page lists active scrap-related auctions with quantity summaries, locations, and official document links.\n\nVerify material grades and yard locations on the official auction portal before bidding.",
  (a) =>
    a.asset_category === "scrap" ||
    a.asset_category === "ewaste" ||
    a.asset_category === "coal" ||
    a.display_material_category?.includes("scrap") === true,
);
export const metadata: Metadata = landing.metadata;
export default function ScrapLandingPage() {
  return landing.page;
}
