import type { Metadata } from "next";
import { MaterialHubApp } from "@/components/material-hub-app";
import { DISPLAY_MATERIAL_CATEGORIES } from "@/lib/display-enrichment";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export function generateStaticParams() {
  return DISPLAY_MATERIAL_CATEGORIES.filter((m) => m.id !== "All").map((m) => ({
    id: m.id,
  }));
}
export const metadata: Metadata = {
  title: "Material auction hub",
  description: "Browse auctions grouped by material category.",
  ...NOINDEX_METADATA,
};
export default async function MaterialHubPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <MaterialHubApp materialId={id} />{" "}
    </div>
  );
}
