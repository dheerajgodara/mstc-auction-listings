"use client";
import {
  enrichAuctionDisplay,
  materialCategoryLabel,
} from "@/lib/display-enrichment";
import {
  formatCountdown,
  getClosingUrgency,
  parseClosingMs,
} from "@/lib/auction-filters";
import { commodityBorderClass } from "@/lib/commodity-styles";
import { sourceLabel } from "@/lib/discovery-constants";
import { formatDateTime } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
import { Chip } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
export function AuctionTable({
  auctions,
  onSelectAuction,
  watchedIds,
  onToggleWatch,
  density = "comfortable",
  className,
}: {
  auctions: AuctionRecord[];
  onSelectAuction?: (id: string) => void;
  watchedIds?: Set<string>;
  onToggleWatch?: (id: string) => void;
  density?: "comfortable" | "compact";
  className?: string;
}) {
  const compact = density === "compact";
  const now = Date.now();
  return (
    <div className={cn("surface-elevated overflow-hidden", className)}>
      {" "}
      <div className="overflow-x-auto">
        {" "}
        <table className="w-full min-w-[960px] border-collapse text-left text-sm">
          {" "}
          <thead>
            {" "}
            <tr className="border-b border-border bg-card text-xs font-semibold uppercase tracking-wide text-muted-foreground dark:bg-muted">
              {" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>
                Lot / Auction
              </th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>Grade</th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>Qty</th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>
                Start price
              </th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>EMD</th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>
                Location
              </th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>
                Time left
              </th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>Source</th>{" "}
              <th className={cn("px-3", compact ? "py-2" : "py-3")}>
                Status
              </th>{" "}
            </tr>{" "}
          </thead>{" "}
          <tbody>
            {" "}
            {auctions.map((raw) => {
              const a = enrichAuctionDisplay(raw);
              const title =
                a.display_title ?? a.item_summary ?? a.auction_number;
              const grade =
                materialCategoryLabel(a.display_material_category) ??
                a.asset_category ??
                "—";
              const location =
                a.display_location_city && a.display_location_state
                  ? `${a.display_location_city}, ${a.display_location_state}`
                  : (a.display_location_city ?? a.state ?? "—");
              const closingMs = parseClosingMs(a.closing);
              const urgency = getClosingUrgency(a.closing, {
                opening: a.opening,
              });
              const watched = watchedIds?.has(a.id);
              const pulse =
                urgency?.pulse &&
                closingMs &&
                closingMs - now < 2 * 60 * 60 * 1000;
              return (
                <tr
                  key={a.id}
                  className={cn(
                    "border-b border-border transition-colors hover:bg-card dark:hover:bg-muted",
                    commodityBorderClass(a),
                  )}
                >
                  {" "}
                  <td className={cn("px-3", compact ? "py-2" : "py-3")}>
                    {" "}
                    <button
                      type="button"
                      onClick={() => onSelectAuction?.(a.id)}
                      className="max-w-[220px] text-left font-medium text-action hover:underline dark:text-action"
                    >
                      {" "}
                      {title}{" "}
                    </button>{" "}
                    <p className="text-xs text-muted-foreground">
                      {a.auction_number}
                    </p>{" "}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 text-muted-foreground",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {grade}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 tabular-nums",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {" "}
                    {a.display_quantity_summary ?? "—"}{" "}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 tabular-nums font-medium text-foreground dark:text-foreground",
                      pulse && "",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {" "}
                    {a.price_summary ?? "—"}{" "}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 text-xs text-action",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {" "}
                    {a.emd_summary ?? "—"}{" "}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 text-muted-foreground",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {location}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 tabular-nums font-medium text-foreground",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {" "}
                    {closingMs && closingMs > now
                      ? formatCountdown(closingMs)
                      : formatDateTime(a.closing)}{" "}
                  </td>{" "}
                  <td
                    className={cn(
                      "px-3 text-muted-foreground",
                      compact ? "py-2" : "py-3",
                    )}
                  >
                    {" "}
                    {sourceLabel(a.source ?? "mstc")}{" "}
                  </td>{" "}
                  <td className={cn("px-3", compact ? "py-2" : "py-3")}>
                    {" "}
                    <div className="flex flex-wrap items-center gap-1">
                      {" "}
                      {urgency && (
                        <Chip
                          className={cn(
                            urgency.chipClass,
                            "normal-case tracking-normal",
                          )}
                        >
                          {" "}
                          {urgency.label}{" "}
                        </Chip>
                      )}{" "}
                      {onToggleWatch && (
                        <button
                          type="button"
                          onClick={() => onToggleWatch(a.id)}
                          className={cn(
                            "text-xs font-medium",
                            watched
                              ? "text-action"
                              : "text-muted-foreground hover:text-action",
                          )}
                        >
                          {" "}
                          {watched ? "★" : "☆"}{" "}
                        </button>
                      )}{" "}
                    </div>{" "}
                  </td>{" "}
                </tr>
              );
            })}{" "}
          </tbody>{" "}
        </table>{" "}
      </div>{" "}
      {auctions.length === 0 && (
        <p className="p-6 text-center text-sm text-muted-foreground">
          No auctions to display.
        </p>
      )}{" "}
    </div>
  );
}
