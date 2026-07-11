"use client";
import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AuctionCard } from "@/components/auction-card";
import type { AuctionRecord } from "@/types/auction";
import { cn } from "@/lib/utils";
export function VirtualizedAuctionList({
  auctions,
  watchedIds,
  onToggleWatch,
  density = "comfortable",
  onOpenDiligence,
  onToggleCompare,
  compareIds,
  searchQuery,
  className,
}: {
  auctions: AuctionRecord[];
  watchedIds?: Set<string>;
  onToggleWatch?: (id: string) => void;
  density?: "comfortable" | "compact";
  onOpenDiligence?: (id: string) => void;
  onToggleCompare?: (id: string) => void;
  compareIds?: string[];
  searchQuery?: string;
  className?: string;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const estimateSize = density === "compact" ? 280 : 420;
  const virtualizer = useVirtualizer({
    count: auctions.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan: 4,
  });
  return (
    <div
      ref={parentRef}
      className={cn("h-[min(80vh,1200px)] overflow-y-auto", className)}
      role="list"
      aria-label="Auction listings"
    >
      {" "}
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {" "}
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const auction = auctions[virtualRow.index];
          return (
            <div
              key={auction.id}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
              className="pb-4"
              role="listitem"
            >
              {" "}
              <AuctionCard
                auction={auction}
                index={virtualRow.index}
                watched={watchedIds?.has(auction.id)}
                onToggleWatch={onToggleWatch}
                compact={density === "compact"}
                onOpenDiligence={
                  onOpenDiligence
                    ? () => onOpenDiligence(auction.id)
                    : undefined
                }
                onToggleCompare={
                  onToggleCompare
                    ? () => onToggleCompare(auction.id)
                    : undefined
                }
                inCompare={compareIds?.includes(auction.id)}
                searchQuery={searchQuery}
              />{" "}
            </div>
          );
        })}{" "}
      </div>{" "}
      {auctions.length === 0 && (
        <p className="p-8 text-center text-sm text-muted-foreground">
          No auctions match your filters.
        </p>
      )}{" "}
    </div>
  );
}
