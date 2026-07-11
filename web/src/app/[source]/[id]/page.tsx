import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AuctionDetailPageApp } from "@/components/auction-detail-page-app";
import {
  getAuctionByRoute,
  getRouteEntry,
  loadRoutesForStaticParams,
} from "@/lib/load-auction-at-build";
import { buildAuctionDescription, buildAuctionTitle } from "@/lib/seo/meta";
import { auctionCanonicalUrl } from "@/lib/seo/auction-url";
import { isValidSourceSlug } from "@/lib/seo/source-slug";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
type PageProps = { params: Promise<{ source: string; id: string }> };
export function generateStaticParams() {
  return loadRoutesForStaticParams();
}
export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { source, id } = await params;
  if (!isValidSourceSlug(source)) return {};
  const auction = getAuctionByRoute(source, id);
  if (!auction) return {};
  const enriched = enrichAuctionDisplay(auction);
  const route = getRouteEntry(source, id);
  const indexable = route?.indexable !== false;
  return {
    title: buildAuctionTitle(enriched),
    description: buildAuctionDescription(enriched),
    alternates: { canonical: auctionCanonicalUrl(enriched) },
    robots: indexable
      ? { index: true, follow: true }
      : { index: false, follow: true },
    openGraph: {
      title: buildAuctionTitle(enriched),
      description: buildAuctionDescription(enriched),
      url: auctionCanonicalUrl(enriched),
      type: "website",
    },
  };
}
export default async function AuctionDetailRoute({ params }: PageProps) {
  const { source, id } = await params;
  if (!isValidSourceSlug(source)) notFound();
  const auction = getAuctionByRoute(source, id);
  if (!auction) notFound();
  return <AuctionDetailPageApp auction={auction} />;
}
