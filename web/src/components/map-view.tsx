"use client";
import dynamic from "next/dynamic";
import type { AuctionRecord } from "@/types/auction";
export const MapView = dynamic(
  () => import("@/components/map-view-client").then((m) => m.MapViewClient),
  {
    ssr: false,
    loading: () => (
      <div className="surface-elevated flex h-[480px] items-center justify-center">
        {" "}
        <p className="text-sm text-muted-foreground">Loading map…</p>{" "}
      </div>
    ),
  },
);
export type MapViewProps = {
  auctions: AuctionRecord[];
  onSelectAuction?: (id: string) => void;
  className?: string;
};
