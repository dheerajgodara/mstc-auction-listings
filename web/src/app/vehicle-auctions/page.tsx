import type { Metadata } from "next";
import { buildMaterialLanding } from "@/lib/seo/material-landings";
const landing = buildMaterialLanding(
  "/vehicle-auctions/",
  "Government Vehicle Auctions India",
  "PSU and government vehicle auctions — cars, trucks, buses, and fleet disposals.",
  "Government vehicle auctions dispose of fleet vehicles, accident/scrap vehicles, and surplus transport assets. Listings include inspection dates, locations, and floor prices where disclosed.\n\nPhysical inspection is strongly recommended before bidding on vehicles.",
  (a) =>
    a.asset_category === "vehicle" ||
    a.display_material_category === "vehicle_lot",
);
export const metadata: Metadata = landing.metadata;
export default function VehicleAuctionsLandingPage() {
  return landing.page;
}
