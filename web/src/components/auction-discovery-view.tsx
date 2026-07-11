"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Clock } from "lucide-react";
import {
  ActiveFilterBar,
  buildActiveFilterChips,
} from "@/components/active-filter-bar";
import { AuctionCard } from "@/components/auction-card";
import { AuctionTable } from "@/components/auction-table";
import { CommandPalette } from "@/components/command-palette";
import { CommodityIndexWidget } from "@/components/commodity-index-widget";
import { CompareTray } from "@/components/compare-tray";
import { DiligencePanel } from "@/components/diligence-panel";
import { DiscoveryActionBar } from "@/components/discovery-action-bar";
import { DiscoveryToolbar } from "@/components/discovery-toolbar";
import { EndingSoonArena } from "@/components/ending-soon-arena";
import { FilterDrawer } from "@/components/filter-drawer";
import { HomeModules } from "@/components/home-modules";
import { IndustrialBeltTiles } from "@/components/industrial-belt-tiles";
import { MarketPulseTicker } from "@/components/market-pulse-ticker";
import { PaginationBar } from "@/components/pagination-bar";
import { VirtualizedAuctionList } from "@/components/virtualized-auction-list";
import { Chip } from "@/components/ui/primitives";
import { useAuctionDiscovery } from "@/hooks/use-auction-discovery";
import { trackEvent, trackNoResults } from "@/lib/analytics";
import { auctionDetailPath } from "@/lib/seo/auction-url";
import { formatDateTime, resolveAppPath, resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";

const MAX_COMPARE = 4;

export function AuctionDiscoveryView({
  auctions,
  total,
  generatedAt,
  automationRanAt,
  showHomeModules = true,
  showHero = true,
  heroTitle = "Discover auctions",
  heroDescription = "Search and filter MSTC, GeM Forward, and eAuction listings — filter, compare, and review diligence before you bid on official portals.",
  paletteOpen: paletteOpenProp,
  onPaletteOpenChange,
}: {
  auctions: AuctionRecord[];
  total?: number;
  generatedAt?: string;
  automationRanAt?: string;
  showHomeModules?: boolean;
  showHero?: boolean;
  heroTitle?: string;
  heroDescription?: string;
  paletteOpen?: boolean;
  onPaletteOpenChange?: (open: boolean) => void;
}) {
  const router = useRouter();
  const d = useAuctionDiscovery(auctions);
  const [paletteOpenInternal, setPaletteOpenInternal] = useState(false);
  const paletteOpen = paletteOpenProp ?? paletteOpenInternal;
  const setPaletteOpen = useCallback(
    (open: boolean) => {
      if (onPaletteOpenChange) onPaletteOpenChange(open);
      else setPaletteOpenInternal(open);
    },
    [onPaletteOpenChange],
  );
  const [diligenceId, setDiligenceId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  const auctionById = useMemo(() => {
    const map = new Map<string, AuctionRecord>();
    for (const a of auctions) map.set(a.id, a);
    return map;
  }, [auctions]);

  const navigateToAuction = useCallback(
    (id: string) => {
      const auction = auctionById.get(id);
      if (!auction) return;
      router.push(resolveAppPath(auctionDetailPath(auction)));
    },
    [auctionById, router],
  );

  const handleToggleCompare = useCallback((id: string) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) {
        const next = prev.filter((x) => x !== id);
        trackEvent("compare_remove", {
          auction_id: id,
          compare_count: next.length,
        });
        return next;
      }
      if (prev.length >= MAX_COMPARE) return prev;
      const next = [...prev, id];
      trackEvent("compare_add", {
        auction_id: id,
        compare_count: next.length,
      });
      return next;
    });
  }, []);

  const compareAuctions = useMemo(
    () =>
      compareIds
        .map((id) => auctionById.get(id))
        .filter((a): a is AuctionRecord => Boolean(a)),
    [compareIds, auctionById],
  );

  const diligenceAuction = diligenceId
    ? (auctionById.get(diligenceId) ?? null)
    : null;

  const activeChips = useMemo(
    () =>
      buildActiveFilterChips({
        query: d.query,
        setQuery: d.setQuery,
        ...d.filterValues,
        ...d.filterSetters,
      }),
    [d],
  );

  useEffect(() => {
    if (!d.debouncedQuery.trim()) return;
    trackEvent("search", {
      search_term: d.debouncedQuery.trim().slice(0, 100),
    });
  }, [d.debouncedQuery]);

  useEffect(() => {
    if (d.sorted.length > 0) return;
    if (!d.debouncedQuery.trim() && activeChips.length === 0) return;
    trackNoResults(Boolean(d.debouncedQuery.trim()), activeChips.length);
  }, [d.sorted.length, d.debouncedQuery, activeChips.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, setPaletteOpen]);

  const statusPageHref = resolvePublicUrl("status/");
  const resultTotal = total ?? auctions.length;

  return (
    <div className="space-y-4 pb-24">
      <MarketPulseTicker auctions={auctions} />

      {showHero && (
      <header className="container-marketplace space-y-2 pb-2 pt-4 sm:pt-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <h1 className="text-display text-foreground">{heroTitle}</h1>
            <p className="max-w-2xl text-body text-muted-foreground">
              {heroDescription}{" "}
              <a
                href={statusPageHref}
                className="font-medium link-action hover:underline"
              >
                Learn more
              </a>
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            {automationRanAt && (
              <Chip className="border-border bg-muted text-muted-foreground normal-case tracking-normal">
                <Clock className="mr-1 inline h-3 w-3" />
                Updated {formatDateTime(automationRanAt)}
              </Chip>
            )}
            {generatedAt && (
              <p className="text-footnote text-muted-foreground">
                Data generated {formatDateTime(generatedAt)}
              </p>
            )}
          </div>
        </div>
      </header>
      )}

      {showHomeModules && (
        <div className="container-marketplace space-y-[var(--space-56)] py-[var(--space-16)]">
          <EndingSoonArena auctions={auctions} />
          <div className="grid gap-4 lg:grid-cols-2">
            <CommodityIndexWidget />
            <IndustrialBeltTiles />
          </div>
          <HomeModules
            auctions={auctions}
            onSelectAuction={navigateToAuction}
          />
        </div>
      )}

      <div className="container-marketplace">
        <div className="flex flex-col gap-4 lg:flex-row">
          <FilterDrawer
            open={d.filtersOpen}
            filters={d.filterValues}
            setters={d.filterSetters}
            facetCounts={d.facetCounts}
            regionOptions={d.regions}
            stateOptions={d.states}
            cityOptions={d.cities}
            onClose={() => d.setFiltersOpen(false)}
            onReset={d.clearAllFilters}
            className="lg:w-72 lg:shrink-0"
          />

          <div className="min-w-0 flex-1 space-y-3">
            <div className="sticky top-[var(--nav-height-regular)] z-sticky space-y-2">
              <DiscoveryToolbar
                query={d.query}
                onQueryChange={d.setQuery}
                sortBy={d.sortBy}
                onSortChange={d.setSortBy}
                density={d.density}
                onDensityChange={d.setDensity}
                viewMode={d.viewMode}
                onViewModeChange={d.setViewMode}
                filtersOpen={d.filtersOpen}
                onToggleFilters={() => d.setFiltersOpen((o) => !o)}
                onOpenCommandPalette={() => setPaletteOpen(true)}
                onSaveSearch={() => d.saveCurrentSearch()}
                resultCount={d.sorted.length}
                totalCount={resultTotal}
              />
              <ActiveFilterBar
                chips={activeChips}
                onClearAll={d.clearAllFilters}
              />
            </div>

            {d.sorted.length === 0 ? (
              <div className="surface-elevated p-8 text-center">
                <p className="text-body font-medium text-foreground">
                  No auctions match your filters
                </p>
                <p className="mt-2 text-body-sm text-muted-foreground">
                  Try clearing filters or browse all listings.
                </p>
                <button
                  type="button"
                  onClick={d.clearAllFilters}
                  className="btn-secondary mt-4"
                >
                  Clear all filters
                </button>
              </div>
            ) : d.viewMode === "table" ? (
              <AuctionTable
                auctions={d.paginated}
                onSelectAuction={navigateToAuction}
                watchedIds={d.watchlist}
                onToggleWatch={d.onToggleWatch}
                density={d.density}
              />
            ) : d.useVirtualList ? (
              <VirtualizedAuctionList
                auctions={d.paginated}
                watchedIds={d.watchlist}
                onToggleWatch={d.onToggleWatch}
                density={d.density}
                onOpenDiligence={(id) => {
                  trackEvent("diligence_open", { auction_id: id });
                  setDiligenceId(id);
                }}
                onToggleCompare={handleToggleCompare}
                compareIds={compareIds}
                searchQuery={d.debouncedQuery}
              />
            ) : (
              <div
                className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
                role="list"
                aria-label="Auction listings"
              >
                {d.paginated.map((auction, index) => (
                  <div key={auction.id} role="listitem">
                    <AuctionCard
                      auction={auction}
                      index={index}
                      watched={d.watchlist.has(auction.id)}
                      onToggleWatch={d.onToggleWatch}
                      compact={d.density === "compact"}
                      onOpenDiligence={() => {
                        trackEvent("diligence_open", { auction_id: auction.id });
                        setDiligenceId(auction.id);
                      }}
                      onToggleCompare={() => handleToggleCompare(auction.id)}
                      inCompare={compareIds.includes(auction.id)}
                      searchQuery={d.debouncedQuery}
                    />
                  </div>
                ))}
              </div>
            )}

            <PaginationBar
              page={d.safePage}
              pageSize={d.pageSize}
              totalItems={d.sorted.length}
              onPageChange={d.setPage}
              onPageSizeChange={d.setPageSize}
            />
          </div>
        </div>
      </div>

      <DiscoveryActionBar
        activeFilterCount={activeChips.length}
        watchlistCount={d.watchlist.size}
        nextClosingMs={d.nextClosingMs}
      />

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        auctions={auctions}
        onSelectAuction={navigateToAuction}
        onApplySavedSearch={d.applySavedSearch}
      />

      {diligenceAuction && (
        <DiligencePanel
          auction={diligenceAuction}
          onClose={() => setDiligenceId(null)}
          searchQuery={d.debouncedQuery}
        />
      )}

      <CompareTray
        auctions={compareAuctions}
        onRemove={(id) =>
          setCompareIds((prev) => prev.filter((x) => x !== id))
        }
        onClear={() => setCompareIds([])}
        onOpenCompare={() => {
          if (compareAuctions[0]) navigateToAuction(compareAuctions[0].id);
        }}
      />
    </div>
  );
}
