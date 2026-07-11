"use client";
import { Clock, Filter } from "lucide-react";
import { formatCountdown } from "@/lib/auction-filters";
import { cn } from "@/lib/utils";
export function DiscoveryActionBar({
  activeFilterCount,
  watchlistCount,
  nextClosingMs,
  className,
}: {
  activeFilterCount: number;
  watchlistCount: number;
  nextClosingMs: number | null;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-2 border-t border-border bg-card px-4 py-2 text-xs text-muted-foreground sm:hidden",
        className,
      )}
    >
      {" "}
      <div className="flex flex-wrap items-center gap-3">
        {" "}
        {activeFilterCount > 0 && (
          <span className="inline-flex items-center gap-1">
            {" "}
            <Filter className="h-3.5 w-3.5" aria-hidden /> {activeFilterCount}{" "}
            filter{activeFilterCount !== 1 ? "s" : ""}{" "}
          </span>
        )}{" "}
        {watchlistCount > 0 && <span> {watchlistCount} watchlist </span>}{" "}
        {nextClosingMs !== null && (
          <span className="inline-flex items-center gap-1 tabular-nums text-foreground">
            {" "}
            <Clock className="h-3.5 w-3.5" aria-hidden /> Next close{" "}
            {formatCountdown(nextClosingMs)}{" "}
          </span>
        )}{" "}
      </div>{" "}
    </div>
  );
}
