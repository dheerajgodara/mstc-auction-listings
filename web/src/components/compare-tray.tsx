"use client";
import { ArrowRight, Scale, X } from "lucide-react";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { formatDateTime } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
import { cn } from "@/lib/utils";
const MAX_COMPARE = 4;
export function CompareTray({
  auctions,
  onRemove,
  onClear,
  onOpenCompare,
  className,
}: {
  auctions: AuctionRecord[];
  onRemove: (id: string) => void;
  onClear: () => void;
  onOpenCompare: () => void;
  className?: string;
}) {
  if (auctions.length === 0) return null;
  return (
    <div
      className={cn(
        "fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 px-4 py-3 shadow-subtle backdrop-blur-sm",
        className,
      )}
      role="region"
      aria-label="Compare tray"
    >
      {" "}
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
        {" "}
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          {" "}
          <Scale className="h-4 w-4 text-muted-foreground" /> Compare (
          {auctions.length}/{MAX_COMPARE}){" "}
        </div>{" "}
        <div className="flex min-w-0 flex-1 flex-wrap gap-2">
          {" "}
          {auctions.map((raw) => {
            const a = enrichAuctionDisplay(raw);
            const title = a.display_title ?? a.item_summary ?? a.auction_number;
            return (
              <div
                key={a.id}
                className="flex max-w-xs items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-xs"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">
                    {title}
                  </p>
                  <p className="truncate tabular-nums text-muted-foreground">
                    Closes {formatDateTime(a.closing)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onRemove(a.id)}
                  className="btn-secondary !min-h-[36px] !min-w-[36px] !rounded-full !p-0"
                  aria-label={`Remove ${a.auction_number} from compare`}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            );
          })}{" "}
        </div>{" "}
        <div className="flex items-center gap-2">
          {" "}
          <button
            type="button"
            onClick={onClear}
            className="btn-secondary text-xs"
          >
            {" "}
            Clear{" "}
          </button>{" "}
          <button
            type="button"
            onClick={onOpenCompare}
            disabled={auctions.length < 2}
            className="btn-primary inline-flex items-center gap-1 text-xs disabled:opacity-50"
          >
            {" "}
            Open compare <ArrowRight className="h-3.5 w-3.5" />{" "}
          </button>{" "}
        </div>{" "}
      </div>{" "}
    </div>
  );
}
export { MAX_COMPARE };
