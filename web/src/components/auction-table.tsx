"use client";

import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import {
  formatCountdown,
  getClosingUrgency,
  parseClosingMs,
} from "@/lib/auction-filters";
import { commodityBorderClass } from "@/lib/commodity-styles";
import { buildTableIdentity, tableClampedPrimary } from "@/lib/table-identity";
import { formatDateTime, cn } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";

function closesTextClass(urgency: ReturnType<typeof getClosingUrgency>): string {
  if (!urgency) return "text-foreground";
  if (urgency.chipClass.includes("rose")) return "text-rose-700 dark:text-rose-400";
  if (urgency.chipClass.includes("amber")) return "text-amber-700 dark:text-amber-400";
  if (urgency.chipClass.includes("muted")) return "text-muted-foreground";
  return "text-foreground";
}

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
  const cellY = compact ? "py-2" : "py-3";

  return (
    <div className={cn("surface-elevated overflow-hidden", className)}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-card text-xs font-semibold uppercase tracking-wide text-muted-foreground dark:bg-muted">
              <th className={cn("px-3", cellY)}>Auction</th>
              <th className={cn("px-3 text-right", cellY)}>Qty</th>
              <th className={cn("px-3 text-right", cellY)}>Price</th>
              <th className={cn("px-3", cellY)}>Location</th>
              <th className={cn("px-3 text-right", cellY)}>Closes</th>
            </tr>
          </thead>
          <tbody>
            {auctions.map((raw) => {
              const a = enrichAuctionDisplay(raw);
              const identity = buildTableIdentity(a);
              const location =
                a.display_location_city && a.display_location_state
                  ? `${a.display_location_city}, ${a.display_location_state}`
                  : (a.display_location_city ?? a.state ?? null);
              const qty = tableClampedPrimary(a.display_quantity_summary, 28);
              const loc = tableClampedPrimary(location, 32);
              const pricePrimary = tableClampedPrimary(a.price_summary, 28);
              const emd = (a.emd_summary ?? "").trim();
              const closingMs = parseClosingMs(a.closing);
              const urgency = getClosingUrgency(a.closing, {
                opening: a.opening,
              });
              const watched = watchedIds?.has(a.id);
              const closesFull =
                closingMs && closingMs > now
                  ? formatCountdown(closingMs)
                  : formatDateTime(a.closing);
              const closes = tableClampedPrimary(closesFull, 18);

              return (
                <tr
                  key={a.id}
                  className={cn(
                    "border-b border-border transition-colors hover:bg-card dark:hover:bg-muted",
                    commodityBorderClass(a),
                  )}
                >
                  <td className={cn("px-3", cellY)}>
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <button
                          type="button"
                          onClick={() => onSelectAuction?.(a.id)}
                          title={
                            identity.secondaryTooltip
                              ? identity.primary !== identity.primaryFull
                                ? `${identity.primaryFull}\n${identity.secondaryTooltip}`
                                : identity.secondaryTooltip
                              : identity.primary !== identity.primaryFull
                                ? identity.primaryFull
                                : undefined
                          }
                          className="max-w-[280px] text-left text-sm font-medium leading-snug text-action hover:underline dark:text-action line-clamp-2"
                        >
                          {identity.primary}
                        </button>
                        {identity.secondary ? (
                          <p
                            className="mt-0.5 text-xs tabular-nums text-muted-foreground"
                            title={identity.secondaryTooltip ?? undefined}
                          >
                            {identity.secondary}
                          </p>
                        ) : null}
                        {identity.tertiary ? (
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {identity.tertiary}
                          </p>
                        ) : null}
                      </div>
                      {onToggleWatch ? (
                        <button
                          type="button"
                          onClick={() => onToggleWatch(a.id)}
                          aria-label={
                            watched ? "Unwatch auction" : "Watch auction"
                          }
                          className={cn(
                            "shrink-0 pt-0.5 text-sm font-medium",
                            watched
                              ? "text-action"
                              : "text-muted-foreground hover:text-action",
                          )}
                        >
                          {watched ? "★" : "☆"}
                        </button>
                      ) : null}
                    </div>
                  </td>
                  <td
                    className={cn(
                      "px-3 text-right tabular-nums text-sm font-medium text-foreground",
                      cellY,
                    )}
                    title={qty.title}
                  >
                    {qty.display}
                  </td>
                  <td className={cn("px-3 text-right", cellY)}>
                    <p
                      className="tabular-nums text-sm font-medium text-foreground"
                      title={pricePrimary.title}
                    >
                      {pricePrimary.display}
                    </p>
                    {emd ? (
                      <p
                        className="mt-0.5 text-xs text-muted-foreground"
                        title={emd.length > 36 ? emd : undefined}
                      >
                        EMD {emd.length > 36 ? `${emd.slice(0, 35)}…` : emd}
                      </p>
                    ) : null}
                  </td>
                  <td
                    className={cn(
                      "px-3 text-sm text-muted-foreground",
                      cellY,
                    )}
                    title={loc.title}
                  >
                    {loc.display}
                  </td>
                  <td
                    className={cn(
                      "px-3 text-right tabular-nums text-sm font-medium",
                      cellY,
                      closesTextClass(urgency),
                    )}
                    title={
                      closes.title ??
                      (a.closing ? formatDateTime(a.closing) : undefined)
                    }
                  >
                    {closes.display}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {auctions.length === 0 && (
        <p className="p-6 text-center text-sm text-muted-foreground">
          No auctions to display.
        </p>
      )}
    </div>
  );
}
