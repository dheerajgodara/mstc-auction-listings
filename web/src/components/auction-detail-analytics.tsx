"use client";
import { useEffect } from "react";
import { trackDetailPageView } from "@/lib/analytics";
export function AuctionDetailAnalytics({
  auctionId,
  source,
}: {
  auctionId: string;
  source?: string;
}) {
  useEffect(() => {
    trackDetailPageView(auctionId, source);
  }, [auctionId, source]);
  return null;
}
