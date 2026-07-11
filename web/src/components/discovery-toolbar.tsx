"use client";

import {
  Bookmark,
  Command,
  Filter,
  LayoutGrid,
  List,
  Rows3,
  Search,
} from "lucide-react";
import { Input, Select } from "@/components/ui/primitives";
import type { SortOption } from "@/lib/auction-filters";
import {
  DENSITY_OPTIONS,
  SORT_OPTIONS,
  VIEW_MODE_OPTIONS,
  type Density,
  type ViewMode,
} from "@/lib/discovery-constants";
import { trackEvent } from "@/lib/analytics";
import { cn } from "@/lib/utils";

export function DiscoveryToolbar({
  query,
  onQueryChange,
  sortBy,
  onSortChange,
  density,
  onDensityChange,
  viewMode,
  onViewModeChange,
  filtersOpen,
  onToggleFilters,
  onOpenCommandPalette,
  onSaveSearch,
  resultCount,
  totalCount,
  className,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  sortBy: SortOption;
  onSortChange: (v: SortOption) => void;
  density: Density;
  onDensityChange: (v: Density) => void;
  viewMode: ViewMode;
  onViewModeChange: (v: ViewMode) => void;
  filtersOpen: boolean;
  onToggleFilters: () => void;
  onOpenCommandPalette: () => void;
  onSaveSearch?: () => void;
  resultCount: number;
  totalCount: number;
  className?: string;
}) {
  const segmentSelected =
    "bg-card text-action shadow-sm dark:bg-muted";

  return (
    <div className={cn("surface-elevated p-[var(--space-12)]", className)}>
      <div className="flex flex-wrap items-center gap-[var(--space-8)]">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="h-10 pl-9 text-body"
            placeholder="Search item, seller, location…"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            aria-label="Search auctions"
          />
        </div>
        <Select
          value={sortBy}
          onChange={(e) => {
            const next = e.target.value as SortOption;
            onSortChange(next);
            trackEvent("sort_change", { sort: next });
          }}
          className="h-10 w-auto min-w-[140px] text-sm"
          aria-label="Sort auctions"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </Select>
        <div
          className="hidden items-center gap-0.5 rounded-lg border border-border bg-card p-0.5 sm:flex"
          role="group"
          aria-label="Density"
        >
          {DENSITY_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => onDensityChange(o.id)}
              className={cn(
                "inline-flex min-h-[36px] items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                density === o.id
                  ? segmentSelected
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={density === o.id}
            >
              <Rows3 className="h-3.5 w-3.5" />
              {o.label}
            </button>
          ))}
        </div>
        <div
          className="flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5"
          role="group"
          aria-label="View mode"
        >
          {VIEW_MODE_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => onViewModeChange(o.id)}
              className={cn(
                "inline-flex min-h-[36px] items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                viewMode === o.id
                  ? segmentSelected
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={viewMode === o.id}
              aria-label={o.label}
            >
              {o.id === "cards" ? (
                <LayoutGrid className="h-3.5 w-3.5" />
              ) : (
                <List className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">{o.label}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onToggleFilters}
          className={cn(
            "btn-secondary inline-flex h-10 items-center gap-1.5 px-3 text-sm",
            filtersOpen && "border-action bg-muted text-action",
          )}
          aria-expanded={filtersOpen}
        >
          <Filter className="h-4 w-4" />
          <span className="hidden sm:inline">Filters</span>
        </button>
        {onSaveSearch ? (
          <button
            type="button"
            onClick={onSaveSearch}
            className="btn-secondary inline-flex h-10 items-center gap-1.5 px-3 text-sm"
            aria-label="Save current search"
          >
            <Bookmark className="h-4 w-4" />
            <span className="hidden sm:inline">Save search</span>
          </button>
        ) : null}
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="btn-secondary inline-flex h-10 items-center gap-1.5 px-3 text-sm"
          aria-label="Open command palette"
        >
          <Command className="h-4 w-4" />
          <kbd className="hidden rounded border border-border bg-card px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline">
            ⌘K
          </kbd>
        </button>
        <p
          className="text-footnote text-muted-foreground"
          aria-live="polite"
          aria-atomic="true"
        >
          <span className="tabular-nums font-medium text-foreground">
            {resultCount}
          </span>
          {" of "}
          <span className="tabular-nums">{totalCount}</span>
          <span className="sr-only"> auctions match current filters</span>
        </p>
      </div>
    </div>
  );
}
