"use client";
import { useMemo } from "react";
import { ChevronRight } from "lucide-react";
import {
  isActiveOrUpcoming,
  parseImportedMs,
  parseClosingMs,
} from "@/lib/auction-filters";
import { enrichAuctionDisplay, auctionTotalMt } from "@/lib/display-enrichment";
import { countAuctionDocuments } from "@/lib/auction-documents";
import { SOURCE_LABELS, sourceLabel } from "@/lib/discovery-constants";
import type { AuctionRecord, AuctionSource } from "@/types/auction";
import { cn } from "@/lib/utils";
function ModuleRow({
  title,
  auctions,
  onSelectAuction,
}: {
  title: string;
  auctions: AuctionRecord[];
  onSelectAuction: (id: string) => void;
}) {
  if (auctions.length === 0) return null;
  return (
    <section className="space-y-2">
      {" "}
      <div className="flex items-center justify-between gap-2">
        {" "}
      <h2 className="text-headline text-foreground">{title}</h2>{" "}
        <span className="text-xs text-muted-foreground tabular-nums">
          {auctions.length}
        </span>{" "}
      </div>{" "}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {" "}
        {auctions.map((raw) => {
          const a = enrichAuctionDisplay(raw);
          const titleText =
            a.display_title ?? a.item_summary ?? a.auction_number;
          const city = a.display_location_city ?? a.state ?? a.region;
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => onSelectAuction(a.id)}
              className="surface-elevated min-w-[220px] max-w-[260px] shrink-0 p-3 text-left"
            >
              {" "}
              <p className="line-clamp-2 text-sm font-medium text-foreground">
                {titleText}
              </p>{" "}
              <p className="mt-1 text-xs text-muted-foreground">{city}</p>{" "}
              {a.display_quantity_summary && (
                <p className="mt-1 text-footnote font-medium text-muted-foreground">
                  {a.display_quantity_summary}
                </p>
              )}{" "}
            </button>
          );
        })}{" "}
      </div>{" "}
    </section>
  );
}
function isNewToday(auction: AuctionRecord): boolean {
  const imported = parseImportedMs(auction);
  if (imported == null) return false;
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const today = fmt.format(new Date());
  const importedDay = fmt.format(new Date(imported));
  return importedDay === today;
}
function closesWithin48h(auction: AuctionRecord): boolean {
  const closing = parseClosingMs(auction.closing);
  if (closing == null) return false;
  const now = Date.now();
  const diff = closing - now;
  return diff > 0 && diff <= 48 * 60 * 60 * 1000;
}
function hasPhotos(auction: AuctionRecord): boolean {
  return countAuctionDocuments(auction).photos > 0;
}
export function HomeModules({
  auctions,
  onSelectAuction,
  className,
}: {
  auctions: AuctionRecord[];
  onSelectAuction: (id: string) => void;
  className?: string;
}) {
  const active = useMemo(
    () => auctions.filter((a) => isActiveOrUpcoming(a.closing)),
    [auctions],
  );
  const newToday = useMemo(
    () => active.filter(isNewToday).slice(0, 12),
    [active],
  );
  const closing48h = useMemo(
    () => active.filter(closesWithin48h).slice(0, 12),
    [active],
  );
  const largeLots = useMemo(
    () =>
      active
        .filter((a) => {
          const mt = auctionTotalMt(a);
          return mt != null && mt >= 100;
        })
        .slice(0, 12),
    [active],
  );
  const withPhotos = useMemo(
    () => active.filter(hasPhotos).slice(0, 12),
    [active],
  );
  const perSource = useMemo(() => {
    const sources: AuctionSource[] = ["mstc", "eauction", "gem_forward"];
    return sources
      .map((source) => ({
        source,
        label: SOURCE_LABELS[source],
        items: active
          .filter((a) => (a.source ?? "mstc") === source)
          .slice(0, 8),
      }))
      .filter((row) => row.items.length > 0);
  }, [active]);
  const hasAny =
    newToday.length > 0 ||
    closing48h.length > 0 ||
    largeLots.length > 0 ||
    withPhotos.length > 0 ||
    perSource.length > 0;
  if (!hasAny) return null;
  return (
    <div className={cn("surface-elevated space-y-5 p-4", className)}>
      {" "}
      <div className="flex items-center gap-2">
        {" "}
        <h2 className="text-page-title text-lg">Discover highlights</h2>{" "}
        <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden />
      </div>{" "}
      <ModuleRow
        title="New today"
        auctions={newToday}
        onSelectAuction={onSelectAuction}
      />{" "}
      <ModuleRow
        title="Closing in 48 hours"
        auctions={closing48h}
        onSelectAuction={onSelectAuction}
      />{" "}
      <ModuleRow
        title="Large lots (100+ MT)"
        auctions={largeLots}
        onSelectAuction={onSelectAuction}
      />{" "}
      <ModuleRow
        title="Has photos"
        auctions={withPhotos}
        onSelectAuction={onSelectAuction}
      />{" "}
      {perSource.map((row) => (
        <ModuleRow
          key={row.source}
          title={sourceLabel(row.source)}
          auctions={row.items}
          onSelectAuction={onSelectAuction}
        />
      ))}{" "}
    </div>
  );
}
