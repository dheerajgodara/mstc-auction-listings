import type { Metadata } from "next";
import { RegionHubApp } from "@/components/region-hub-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
export function generateStaticParams() {
  return [
    { slug: "ncr" },
    { slug: "mumbai" },
    { slug: "bengaluru" },
    { slug: "chennai" },
    { slug: "hyderabad" },
    { slug: "kolkata" },
  ];
}
export const metadata: Metadata = {
  title: "Regional auction hub",
  description: "Browse auctions grouped by industrial region.",
  ...NOINDEX_METADATA,
};
export default async function RegionHubPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <RegionHubApp slug={slug} />{" "}
    </div>
  );
}
