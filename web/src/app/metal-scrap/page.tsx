import type { Metadata } from "next";
import { buildMaterialLanding } from "@/lib/seo/material-landings";
const landing = buildMaterialLanding(
  "/metal-scrap/",
  "Metal Scrap Auctions India | Ferrous & Non-Ferrous",
  "Government metal scrap auctions including ferrous scrap, cable scrap, and transmission materials.",
  "Metal scrap auctions cover ferrous scrap (HMS, melting scrap), aluminium conductor, cable scrap, and transmission tower materials from PSUs and utilities. Browse active listings with MT quantities and state-wise locations.\n\nInspection and material testing requirements vary by auction — check official notices.",
  (a) => {
    const m = a.display_material_category ?? "";
    return (
      m.includes("scrap") ||
      m.includes("ferrous") ||
      m.includes("aluminium") ||
      m.includes("cable") ||
      m.includes("transmission")
    );
  },
);
export const metadata: Metadata = landing.metadata;
export default function MetalScrapLandingPage() {
  return landing.page;
}
