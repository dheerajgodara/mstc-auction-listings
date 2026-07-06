"use client";

import { useEffect, useMemo, useState } from "react";
import { Calendar, Clock, Download, Filter, Search, Star, X } from "lucide-react";
import { AuctionCard } from "@/components/auction-card";
import { PaginationBar } from "@/components/pagination-bar";
import { Chip, Input, Select } from "@/components/ui/primitives";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  type DatePreset,
  type ImportedPreset,
  type ListedPreset,
  applySortOption,
  isActiveOrUpcoming,
  isDateFilterActive,
  isImportedFilterActive,
  isListedFilterActive,
  matchesCityFilter,
  matchesClosingDateFilter,
  matchesDisplayStateFilter,
  matchesDocumentsFilter,
  matchesImportedDateFilter,
  matchesLargeLotsOnly,
  matchesListedDateFilter,
  matchesMaterialCategoryFilter,
  matchesQuantityMinFilter,
  type QuantityMinFilter,
  type DocumentsFilter,
  type SortOption,
} from "@/lib/auction-filters";
import { trackEvent } from "@/lib/analytics";
import {
  DISPLAY_MATERIAL_CATEGORIES,
  enrichAuctionDisplay,
  materialCategoryLabel,
} from "@/lib/display-enrichment";
import { auctionsToCsv, downloadCsv } from "@/lib/export-csv";
import { rankAuctionsBySearch } from "@/lib/search";
import {
  deleteSavedSearch,
  loadSavedSearches,
  type SavedSearch,
  upsertSavedSearch,
} from "@/lib/saved-searches";
import { isWatched, loadWatchlist, toggleWatchlist } from "@/lib/watchlist";
import { formatDateTime, resolvePublicUrl } from "@/lib/utils";
import type { AssetCategory, AuctionRecord, AuctionSource, EmdParseStatus } from "@/types/auction";
import { cn } from "@/lib/utils";

const SOURCES = ["All", "mstc", "eauction", "gem_forward"] as const;
const ASSET_CATEGORIES = [
  "All",
  "vehicle",
  "scrap",
  "machinery",
  "ewaste",
  "minerals",
  "timber",
  "property",
  "coal",
  "other",
] as const;

const SOURCE_LABELS: Record<AuctionSource, string> = {
  mstc: "MSTC",
  eauction: "eAuction",
  gem_forward: "GeM Forward",
};

function sourceLabel(source?: AuctionSource | null): string {
  if (!source || source === "mstc") return "MSTC";
  return SOURCE_LABELS[source] ?? source;
}

function categoryLabel(category: AssetCategory): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}

const LOT_TYPES = ["All", "General", "RVSF", "Hazardous"] as const;
const CONFIDENCE = ["All", "high", "medium", "low", "minimal"] as const;
const PRICE_STATUS = [
  "All",
  "numeric",
  "range",
  "percentage_based",
  "not_disclosed",
  "missing",
] as const;
const EMD_STATUS = [
  "All",
  "auction_wise",
  "item_wise",
  "not_required",
  "missing",
  "unknown",
] as const;

const DATE_PRESETS: { id: DatePreset; label: string }[] = [
  { id: "today", label: "Closing today" },
  { id: "tomorrow", label: "Closing tomorrow" },
  { id: "next3", label: "Next 3 days" },
  { id: "next7", label: "Next 7 days" },
];

const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  all: "All dates",
  today: "Closing today",
  tomorrow: "Closing tomorrow",
  next3: "Next 3 days",
  next7: "Next 7 days",
  custom: "Custom range",
};

const LISTED_PRESETS: { id: ListedPreset; label: string }[] = [
  { id: "today", label: "Listed today" },
  { id: "yesterday", label: "Listed yesterday" },
  { id: "last3", label: "Last 3 days" },
  { id: "last7", label: "Last 7 days" },
  { id: "last14", label: "Last 14 days" },
];

const LISTED_PRESET_LABELS: Record<ListedPreset, string> = {
  all: "All listing dates",
  today: "Listed today",
  yesterday: "Listed yesterday",
  last3: "Listed last 3 days",
  last7: "Listed last 7 days",
  last14: "Listed last 14 days",
  custom: "Custom range",
};

const IMPORTED_PRESETS: { id: ImportedPreset; label: string }[] = [
  { id: "today", label: "Imported today" },
  { id: "yesterday", label: "Imported yesterday" },
  { id: "last3", label: "Last 3 days" },
  { id: "last7", label: "Last 7 days" },
];

const IMPORTED_PRESET_LABELS: Record<ImportedPreset, string> = {
  all: "All import dates",
  today: "Imported today",
  yesterday: "Imported yesterday",
  last3: "Imported last 3 days",
  last7: "Imported last 7 days",
  custom: "Custom range",
};

const QUANTITY_MIN_OPTIONS: { id: QuantityMinFilter; label: string }[] = [
  { id: "any", label: "Any quantity" },
  { id: "10", label: "10+ MT" },
  { id: "50", label: "50+ MT" },
  { id: "100", label: "100+ MT" },
  { id: "500", label: "500+ MT" },
  { id: "1000", label: "1000+ MT" },
];

function PillButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50",
        active ? "btn-pill-active" : "btn-pill-inactive",
      )}
    >
      {children}
    </button>
  );
}

function RemovableChip({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onRemove}
      className="inline-flex items-center gap-1 rounded-full border border-cyan-200/80 bg-cyan-50/90 px-2.5 py-1 text-xs font-medium text-cyan-900 hover:bg-cyan-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
    >
      {label}
      <X className="h-3 w-3" />
    </button>
  );
}

export function AuctionListings({
  auctions,
  generatedAt,
  automationRanAt,
  total,
}: {
  auctions: AuctionRecord[];
  generatedAt?: string;
  automationRanAt?: string;
  total?: number;
}) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 200);
  const [sourceFilter, setSourceFilter] = useState<(typeof SOURCES)[number]>("All");
  const [assetCategory, setAssetCategory] =
    useState<(typeof ASSET_CATEGORIES)[number]>("All");
  const [stateFilter, setStateFilter] = useState("All");
  const [regionFilter, setRegionFilter] = useState("All");
  const [lotType, setLotType] = useState<(typeof LOT_TYPES)[number]>("All");
  const [confidence, setConfidence] =
    useState<(typeof CONFIDENCE)[number]>("All");
  const [priceStatus, setPriceStatus] =
    useState<(typeof PRICE_STATUS)[number]>("All");
  const [emdStatus, setEmdStatus] = useState<(typeof EMD_STATUS)[number]>("All");
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [listedPreset, setListedPreset] = useState<ListedPreset>("all");
  const [listedFrom, setListedFrom] = useState("");
  const [listedTo, setListedTo] = useState("");
  const [importedPreset, setImportedPreset] = useState<ImportedPreset>("all");
  const [importedFrom, setImportedFrom] = useState("");
  const [importedTo, setImportedTo] = useState("");
  const [cityFilter, setCityFilter] = useState("All");
  const [materialFilter, setMaterialFilter] = useState("All");
  const [quantityMin, setQuantityMin] = useState<QuantityMinFilter>("any");
  const [largeLotsOnly, setLargeLotsOnly] = useState(false);
  const [documentsFilter, setDocumentsFilter] = useState<DocumentsFilter>("any");
  const [sortBy, setSortBy] = useState<SortOption>("closing_asc");
  const [includeClosed, setIncludeClosed] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [watchlist, setWatchlist] = useState<Set<string>>(() => new Set());
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);

  useEffect(() => {
    setWatchlist(loadWatchlist());
    setSavedSearches(loadSavedSearches());
  }, []);

  useEffect(() => {
    if (!debouncedQuery.trim()) return;
    trackEvent("search", { search_term: debouncedQuery.trim().slice(0, 100) });
  }, [debouncedQuery]);

  const totalCount = total ?? auctions.length;

  const regions = useMemo(() => {
    const r = new Set(auctions.map((a) => a.region).filter(Boolean));
    return ["All", ...Array.from(r).sort()];
  }, [auctions]);

  const states = useMemo(() => {
    const s = new Set<string>();
    for (const a of auctions) {
      const st = enrichAuctionDisplay(a).display_location_state ?? a.state;
      if (st) s.add(st);
    }
    return ["All", ...Array.from(s).sort()];
  }, [auctions]);

  const cities = useMemo(() => {
    const c = new Set<string>();
    for (const a of auctions) {
      const city = enrichAuctionDisplay(a).display_location_city;
      if (city) c.add(city);
    }
    return ["All", ...Array.from(c).sort()];
  }, [auctions]);

  const effectiveDatePreset =
    datePreset === "all" && (customFrom || customTo) ? "custom" : datePreset;
  const effectiveListedPreset =
    listedPreset === "all" && (listedFrom || listedTo) ? "custom" : listedPreset;
  const effectiveImportedPreset =
    importedPreset === "all" && (importedFrom || importedTo) ? "custom" : importedPreset;

  const filtered = useMemo(() => {
    return auctions.filter((a) => {
      if (watchlistOnly && !watchlist.has(a.id)) return false;
      if (!includeClosed && !isActiveOrUpcoming(a.closing)) return false;
      const auctionSource = a.source ?? "mstc";
      if (sourceFilter !== "All" && auctionSource !== sourceFilter) return false;
      if (assetCategory !== "All" && a.asset_category !== assetCategory) return false;
      if (!matchesDisplayStateFilter(a, stateFilter)) return false;
      if (!matchesCityFilter(a, cityFilter)) return false;
      if (!matchesMaterialCategoryFilter(a, materialFilter)) return false;
      if (!matchesQuantityMinFilter(a, quantityMin)) return false;
      if (!matchesLargeLotsOnly(a, largeLotsOnly)) return false;
      if (!matchesDocumentsFilter(a, documentsFilter)) return false;
      if (regionFilter !== "All" && a.region !== regionFilter) return false;
      if (lotType !== "All" && !a.lot_types?.includes(lotType)) return false;
      if (confidence !== "All" && a.parse_confidence !== confidence) return false;
      if (priceStatus !== "All" && a.price_parse_status !== priceStatus) {
        return false;
      }
      if (
        emdStatus !== "All" &&
        a.emd_parse_status !== (emdStatus as EmdParseStatus)
      ) {
        return false;
      }
      if (
        !matchesClosingDateFilter(
          a.closing,
          effectiveDatePreset,
          customFrom,
          customTo,
        )
      ) {
        return false;
      }
      if (
        !matchesListedDateFilter(a, effectiveListedPreset, listedFrom, listedTo)
      ) {
        return false;
      }
      if (
        !matchesImportedDateFilter(
          a,
          effectiveImportedPreset,
          importedFrom,
          importedTo,
        )
      ) {
        return false;
      }
      return true;
    });
  }, [
    auctions,
    watchlistOnly,
    watchlist,
    includeClosed,
    sourceFilter,
    assetCategory,
    stateFilter,
    cityFilter,
    materialFilter,
    quantityMin,
    largeLotsOnly,
    documentsFilter,
    regionFilter,
    lotType,
    confidence,
    priceStatus,
    emdStatus,
    effectiveDatePreset,
    customFrom,
    customTo,
    effectiveListedPreset,
    listedFrom,
    listedTo,
    effectiveImportedPreset,
    importedFrom,
    importedTo,
  ]);

  const sorted = useMemo(() => {
    const base = debouncedQuery.trim()
      ? rankAuctionsBySearch(filtered, debouncedQuery)
      : filtered;
    return applySortOption(base, sortBy);
  }, [filtered, debouncedQuery, sortBy]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, totalPages);

  const paginated = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return sorted.slice(start, start + pageSize);
  }, [sorted, safePage, pageSize]);

  useEffect(() => {
    setPage(1);
  }, [
    debouncedQuery,
    sourceFilter,
    assetCategory,
    stateFilter,
    cityFilter,
    materialFilter,
    quantityMin,
    largeLotsOnly,
    documentsFilter,
    regionFilter,
    lotType,
    confidence,
    priceStatus,
    emdStatus,
    datePreset,
    customFrom,
    customTo,
    listedPreset,
    listedFrom,
    listedTo,
    importedPreset,
    importedFrom,
    importedTo,
    sortBy,
    includeClosed,
    watchlistOnly,
    pageSize,
  ]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const clearAllFilters = () => {
    setQuery("");
    setSourceFilter("All");
    setAssetCategory("All");
    setStateFilter("All");
    setRegionFilter("All");
    setLotType("All");
    setConfidence("All");
    setPriceStatus("All");
    setEmdStatus("All");
    setDatePreset("all");
    setCustomFrom("");
    setCustomTo("");
    setListedPreset("all");
    setListedFrom("");
    setListedTo("");
    setImportedPreset("all");
    setImportedFrom("");
    setImportedTo("");
    setCityFilter("All");
    setMaterialFilter("All");
    setQuantityMin("any");
    setLargeLotsOnly(false);
    setIncludeClosed(true);
    setWatchlistOnly(false);
  };

  const handleToggleWatch = (id: string) => {
    setWatchlist(toggleWatchlist(id));
  };

  const handleExportVisible = () => {
    trackEvent("csv_export", { count: sorted.length });
    downloadCsv(
      `auctions-visible-${new Date().toISOString().slice(0, 10)}.csv`,
      auctionsToCsv(sorted),
    );
  };

  const handleExportWatchlist = () => {
    const saved = auctions.filter((a) => watchlist.has(a.id));
    downloadCsv(
      `auctions-watchlist-${new Date().toISOString().slice(0, 10)}.csv`,
      auctionsToCsv(saved),
    );
  };

  const handleSaveCurrentSearch = () => {
    const name = query.trim() || `Search ${new Date().toLocaleString("en-IN")}`;
    const entry: SavedSearch = {
      id: `ss_${Date.now()}`,
      name,
      createdAt: new Date().toISOString(),
      query,
      sourceFilter,
      assetCategory,
      stateFilter,
      regionFilter,
      lotType,
      confidence,
      priceStatus,
      emdStatus,
      datePreset,
      customFrom,
      customTo,
      listedPreset,
      listedFrom,
      listedTo,
      sortBy,
      includeClosed,
      watchlistOnly,
    };
    setSavedSearches(upsertSavedSearch(entry));
  };

  const applySavedSearch = (saved: SavedSearch) => {
    setQuery(saved.query);
    setSourceFilter(saved.sourceFilter as (typeof SOURCES)[number]);
    setAssetCategory(saved.assetCategory as (typeof ASSET_CATEGORIES)[number]);
    setStateFilter(saved.stateFilter);
    setRegionFilter(saved.regionFilter);
    setLotType(saved.lotType as (typeof LOT_TYPES)[number]);
    setConfidence(saved.confidence as (typeof CONFIDENCE)[number]);
    setPriceStatus(saved.priceStatus as (typeof PRICE_STATUS)[number]);
    setEmdStatus(saved.emdStatus as (typeof EMD_STATUS)[number]);
    setDatePreset(saved.datePreset);
    setCustomFrom(saved.customFrom);
    setCustomTo(saved.customTo);
    setListedPreset(saved.listedPreset ?? "all");
    setListedFrom(saved.listedFrom ?? "");
    setListedTo(saved.listedTo ?? "");
    setSortBy(saved.sortBy);
    setIncludeClosed(saved.includeClosed);
    setWatchlistOnly(saved.watchlistOnly);
  };

  const activeChips = useMemo(() => {
    const chips: { key: string; label: string; onRemove: () => void }[] = [];

    if (query.trim()) {
      chips.push({
        key: "search",
        label: `Search: ${query.trim()}`,
        onRemove: () => setQuery(""),
      });
    }
    if (isDateFilterActive(effectiveDatePreset, customFrom, customTo)) {
      const dateLabel =
        effectiveDatePreset === "custom"
          ? `Dates: ${customFrom || "…"} – ${customTo || "…"}`
          : DATE_PRESET_LABELS[effectiveDatePreset];
      chips.push({
        key: "date",
        label: dateLabel,
        onRemove: () => {
          setDatePreset("all");
          setCustomFrom("");
          setCustomTo("");
        },
      });
    }
    if (isListedFilterActive(effectiveListedPreset, listedFrom, listedTo)) {
      const listedLabel =
        effectiveListedPreset === "custom"
          ? `Listed: ${listedFrom || "…"} – ${listedTo || "…"}`
          : LISTED_PRESET_LABELS[effectiveListedPreset];
      chips.push({
        key: "listed",
        label: listedLabel,
        onRemove: () => {
          setListedPreset("all");
          setListedFrom("");
          setListedTo("");
        },
      });
    }
    if (isImportedFilterActive(effectiveImportedPreset, importedFrom, importedTo)) {
      const importedLabel =
        effectiveImportedPreset === "custom"
          ? `Imported: ${importedFrom || "…"} – ${importedTo || "…"}`
          : IMPORTED_PRESET_LABELS[effectiveImportedPreset];
      chips.push({
        key: "imported",
        label: importedLabel,
        onRemove: () => {
          setImportedPreset("all");
          setImportedFrom("");
          setImportedTo("");
        },
      });
    }
    if (sourceFilter !== "All") {
      chips.push({
        key: "source",
        label: `Source: ${sourceLabel(sourceFilter)}`,
        onRemove: () => setSourceFilter("All"),
      });
    }
    if (assetCategory !== "All") {
      chips.push({
        key: "category",
        label: `Category: ${categoryLabel(assetCategory)}`,
        onRemove: () => setAssetCategory("All"),
      });
    }
    if (stateFilter !== "All") {
      chips.push({
        key: "state",
        label: `State: ${stateFilter}`,
        onRemove: () => setStateFilter("All"),
      });
    }
    if (cityFilter !== "All") {
      chips.push({
        key: "city",
        label: `City: ${cityFilter}`,
        onRemove: () => setCityFilter("All"),
      });
    }
    if (materialFilter !== "All") {
      chips.push({
        key: "material",
        label: `Material: ${materialCategoryLabel(materialFilter) ?? materialFilter}`,
        onRemove: () => setMaterialFilter("All"),
      });
    }
    if (quantityMin !== "any") {
      chips.push({
        key: "quantity",
        label: `Quantity: ${quantityMin}+ MT`,
        onRemove: () => setQuantityMin("any"),
      });
    }
    if (largeLotsOnly) {
      chips.push({
        key: "largeLots",
        label: "Large lots (100+ MT)",
        onRemove: () => setLargeLotsOnly(false),
      });
    }
    if (documentsFilter === "documents") {
      chips.push({
        key: "documents",
        label: "Has documents",
        onRemove: () => setDocumentsFilter("any"),
      });
    }
    if (documentsFilter === "photos") {
      chips.push({
        key: "photos",
        label: "Has photos",
        onRemove: () => setDocumentsFilter("any"),
      });
    }
    if (regionFilter !== "All") {
      chips.push({
        key: "region",
        label: `Region: ${regionFilter}`,
        onRemove: () => setRegionFilter("All"),
      });
    }
    if (confidence !== "All") {
      chips.push({
        key: "confidence",
        label: `Confidence: ${confidence}`,
        onRemove: () => setConfidence("All"),
      });
    }
    if (priceStatus !== "All") {
      chips.push({
        key: "price",
        label: `Price: ${priceStatus.replace(/_/g, " ")}`,
        onRemove: () => setPriceStatus("All"),
      });
    }
    if (emdStatus !== "All") {
      chips.push({
        key: "emd",
        label: `EMD: ${emdStatus.replace(/_/g, " ")}`,
        onRemove: () => setEmdStatus("All"),
      });
    }
    if (lotType !== "All") {
      chips.push({
        key: "lotType",
        label: `Type: ${lotType}`,
        onRemove: () => setLotType("All"),
      });
    }
    if (!includeClosed) {
      chips.push({
        key: "closed",
        label: "Active/upcoming only",
        onRemove: () => setIncludeClosed(true),
      });
    }

    return chips;
  }, [
    query,
    effectiveDatePreset,
    customFrom,
    customTo,
    effectiveListedPreset,
    listedFrom,
    listedTo,
    effectiveImportedPreset,
    importedFrom,
    importedTo,
    sourceFilter,
    assetCategory,
    stateFilter,
    cityFilter,
    materialFilter,
    quantityMin,
    largeLotsOnly,
    documentsFilter,
    regionFilter,
    confidence,
    priceStatus,
    emdStatus,
    lotType,
    includeClosed,
  ]);

  const showCustomRange =
    datePreset === "custom" || Boolean(customFrom || customTo);
  const showListedCustomRange =
    listedPreset === "custom" || Boolean(listedFrom || listedTo);
  const showImportedCustomRange =
    importedPreset === "custom" || Boolean(importedFrom || importedTo);
  const statusPageHref = resolvePublicUrl("status/");

  return (
    <div className="space-y-4">
      <header className="mx-auto max-w-6xl space-y-2 pt-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              Government Auction Listings
            </h1>
            <p className="max-w-2xl text-sm text-slate-600">
              Government auction opportunities from MSTC, GeM Forward, and eAuction.gov.in
              (public ByDate tabs — near-term visible window).{" "}
              <a href={statusPageHref} className="font-medium text-cyan-800 hover:underline">
                Import status
              </a>
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            {automationRanAt && (
              <Chip className="border-violet-200/80 bg-violet-50/90 text-violet-900 normal-case tracking-normal">
                <Clock className="mr-1 inline h-3 w-3" />
                Automation ran: {formatDateTime(automationRanAt)}
              </Chip>
            )}
            {generatedAt && (
              <p className="text-xs text-slate-500">
                Data generated: {formatDateTime(generatedAt)}
              </p>
            )}
          </div>
        </div>
      </header>

      <div className="sticky top-0 z-20 mx-auto max-w-6xl space-y-2">
        <div className="glass-panel p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[200px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cyan-600/70" />
              <Input
                className="h-9 pl-9"
                placeholder="Search item, seller, location…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <Select
              value={sortBy}
              onChange={(e) => {
                const next = e.target.value as SortOption;
                setSortBy(next);
                trackEvent("sort_change", { sort: next });
              }}
              className="h-9 w-auto min-w-[140px] text-sm"
              aria-label="Sort auctions"
            >
              <option value="closing_asc">Closing soonest</option>
              <option value="opening_asc">Opening soonest</option>
              <option value="listed_desc">Recently listed</option>
              <option value="imported_desc">Recently imported</option>
              <option value="quantity_desc">Largest quantity</option>
              <option value="lots_desc">Most lots</option>
              <option value="documents_desc">Most documents</option>
              <option value="price_asc">Price low → high</option>
              <option value="price_desc">Price high → low</option>
              <option value="best_opportunities">Best opportunities</option>
            </Select>
            <button
              type="button"
              onClick={handleExportVisible}
              className="btn-glass inline-flex h-9 items-center gap-1.5 px-3 text-sm"
            >
              <Download className="h-4 w-4" />
              Export CSV
            </button>
            <button
              type="button"
              onClick={handleSaveCurrentSearch}
              className="btn-glass inline-flex h-9 items-center gap-1.5 px-3 text-sm"
            >
              Save search
            </button>
            <button
              type="button"
              onClick={() => setFiltersOpen((v) => !v)}
              className={cn(
                "btn-glass inline-flex h-9 items-center gap-1.5 px-3 text-sm",
                filtersOpen && "btn-pill-active",
              )}
            >
              <Filter className="h-4 w-4" />
              Filters
            </button>
            <Chip className="hidden border-cyan-200/80 bg-cyan-50/90 text-cyan-900 normal-case tracking-normal sm:inline-flex">
              {filtered.length} of {totalCount}
            </Chip>
          </div>

          {activeChips.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-white/50 pt-2">
              {activeChips.map((chip) => (
                <RemovableChip
                  key={chip.key}
                  label={chip.label}
                  onRemove={chip.onRemove}
                />
              ))}
              <button
                type="button"
                onClick={clearAllFilters}
                className="text-xs font-medium text-cyan-800 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
              >
                Clear all
              </button>
            </div>
          )}

          {filtersOpen && (
            <div
              className={cn(
                "space-y-3 border-t border-white/50 pt-3",
                activeChips.length === 0 && "mt-2",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Calendar className="h-4 w-4 shrink-0 text-cyan-600/80" />
                {DATE_PRESETS.map((p) => (
                  <PillButton
                    key={p.id}
                    active={datePreset === p.id}
                    onClick={() => {
                      setDatePreset(p.id);
                      setCustomFrom("");
                      setCustomTo("");
                    }}
                  >
                    {p.label}
                  </PillButton>
                ))}
                <PillButton
                  active={datePreset === "custom"}
                  onClick={() => setDatePreset("custom")}
                >
                  Custom range
                </PillButton>
              </div>

              {showCustomRange && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    From
                    <Input
                      type="date"
                      value={customFrom}
                      onChange={(e) => {
                        setCustomFrom(e.target.value);
                        if (datePreset !== "custom") setDatePreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    To
                    <Input
                      type="date"
                      value={customTo}
                      onChange={(e) => {
                        setCustomTo(e.target.value);
                        if (datePreset !== "custom") setDatePreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Calendar className="h-4 w-4 shrink-0 text-violet-600/80" />
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                  Listed date
                </span>
                {LISTED_PRESETS.map((p) => (
                  <PillButton
                    key={p.id}
                    active={listedPreset === p.id}
                    onClick={() => {
                      setListedPreset(p.id);
                      setListedFrom("");
                      setListedTo("");
                    }}
                  >
                    {p.label}
                  </PillButton>
                ))}
                <PillButton
                  active={listedPreset === "custom"}
                  onClick={() => setListedPreset("custom")}
                >
                  Custom range
                </PillButton>
                {(listedPreset !== "all" || listedFrom || listedTo) && (
                  <button
                    type="button"
                    onClick={() => {
                      setListedPreset("all");
                      setListedFrom("");
                      setListedTo("");
                    }}
                    className="text-xs font-medium text-cyan-800 hover:underline"
                  >
                    Clear
                  </button>
                )}
              </div>

              {showListedCustomRange && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    Listed from
                    <Input
                      type="date"
                      value={listedFrom}
                      onChange={(e) => {
                        setListedFrom(e.target.value);
                        if (listedPreset !== "custom") setListedPreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    Listed to
                    <Input
                      type="date"
                      value={listedTo}
                      onChange={(e) => {
                        setListedTo(e.target.value);
                        if (listedPreset !== "custom") setListedPreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Calendar className="h-4 w-4 shrink-0 text-sky-600/80" />
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                  Imported date
                </span>
                {IMPORTED_PRESETS.map((p) => (
                  <PillButton
                    key={p.id}
                    active={importedPreset === p.id}
                    onClick={() => {
                      setImportedPreset(p.id);
                      setImportedFrom("");
                      setImportedTo("");
                    }}
                  >
                    {p.label}
                  </PillButton>
                ))}
                <PillButton
                  active={importedPreset === "custom"}
                  onClick={() => setImportedPreset("custom")}
                >
                  Custom range
                </PillButton>
                {(importedPreset !== "all" || importedFrom || importedTo) && (
                  <button
                    type="button"
                    onClick={() => {
                      setImportedPreset("all");
                      setImportedFrom("");
                      setImportedTo("");
                    }}
                    className="text-xs font-medium text-cyan-800 hover:underline"
                  >
                    Clear
                  </button>
                )}
              </div>

              {showImportedCustomRange && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    Imported from
                    <Input
                      type="date"
                      value={importedFrom}
                      onChange={(e) => {
                        setImportedFrom(e.target.value);
                        if (importedPreset !== "custom") setImportedPreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    Imported to
                    <Input
                      type="date"
                      value={importedTo}
                      onChange={(e) => {
                        setImportedTo(e.target.value);
                        if (importedPreset !== "custom") setImportedPreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={sourceFilter}
                  onChange={(e) =>
                    setSourceFilter(e.target.value as (typeof SOURCES)[number])
                  }
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {s === "All" ? "All sources" : sourceLabel(s)}
                    </option>
                  ))}
                </Select>
                <Select
                  value={assetCategory}
                  onChange={(e) =>
                    setAssetCategory(e.target.value as (typeof ASSET_CATEGORIES)[number])
                  }
                  className="h-9 w-auto min-w-[130px] text-sm"
                >
                  {ASSET_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c === "All" ? "All categories" : categoryLabel(c)}
                    </option>
                  ))}
                </Select>
                <Select
                  value={stateFilter}
                  onChange={(e) => setStateFilter(e.target.value)}
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {states.map((s) => (
                    <option key={s} value={s}>
                      {s === "All" ? "All states" : s}
                    </option>
                  ))}
                </Select>
                <Select
                  value={cityFilter}
                  onChange={(e) => setCityFilter(e.target.value)}
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {cities.map((c) => (
                    <option key={c} value={c}>
                      {c === "All" ? "All cities" : c}
                    </option>
                  ))}
                </Select>
                <Select
                  value={materialFilter}
                  onChange={(e) => setMaterialFilter(e.target.value)}
                  className="h-9 w-auto min-w-[140px] text-sm"
                >
                  {DISPLAY_MATERIAL_CATEGORIES.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </Select>
                <Select
                  value={quantityMin}
                  onChange={(e) => setQuantityMin(e.target.value as QuantityMinFilter)}
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {QUANTITY_MIN_OPTIONS.map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.label}
                    </option>
                  ))}
                </Select>
                <Select
                  value={regionFilter}
                  onChange={(e) => setRegionFilter(e.target.value)}
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {regions.map((r) => (
                    <option key={r} value={r}>
                      {r === "All" ? "All regions" : r}
                    </option>
                  ))}
                </Select>
                <Select
                  value={lotType}
                  onChange={(e) =>
                    setLotType(e.target.value as (typeof LOT_TYPES)[number])
                  }
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {LOT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t === "All" ? "All types" : t}
                    </option>
                  ))}
                </Select>
                <Select
                  value={confidence}
                  onChange={(e) =>
                    setConfidence(e.target.value as (typeof CONFIDENCE)[number])
                  }
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {CONFIDENCE.map((c) => (
                    <option key={c} value={c}>
                      {c === "All" ? "All confidence" : c}
                    </option>
                  ))}
                </Select>
                <Select
                  value={priceStatus}
                  onChange={(e) =>
                    setPriceStatus(e.target.value as (typeof PRICE_STATUS)[number])
                  }
                  className="h-9 w-auto min-w-[130px] text-sm"
                >
                  {PRICE_STATUS.map((p) => (
                    <option key={p} value={p}>
                      {p === "All" ? "All prices" : p.replace(/_/g, " ")}
                    </option>
                  ))}
                </Select>
                <Select
                  value={emdStatus}
                  onChange={(e) =>
                    setEmdStatus(e.target.value as (typeof EMD_STATUS)[number])
                  }
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {EMD_STATUS.map((e) => (
                    <option key={e} value={e}>
                      {e === "All" ? "All EMD" : e.replace(/_/g, " ")}
                    </option>
                  ))}
                </Select>
              </div>

              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={includeClosed}
                  onChange={(e) => setIncludeClosed(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-400/50"
                />
                Include recently closed auctions
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={watchlistOnly}
                  onChange={(e) => setWatchlistOnly(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-amber-600 focus:ring-amber-400/50"
                />
                <Star className="h-4 w-4 text-amber-600" />
                Watchlist only ({watchlist.size})
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={largeLotsOnly}
                  onChange={(e) => {
                    setLargeLotsOnly(e.target.checked);
                    trackEvent("filter_change", { filter: "large_lots", value: e.target.checked });
                  }}
                  className="h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-400/50"
                />
                Large lots only (100+ MT)
              </label>
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-600">Documents / photos</span>
                <Select
                  value={documentsFilter}
                  onChange={(e) => {
                    const next = e.target.value as DocumentsFilter;
                    setDocumentsFilter(next);
                    trackEvent("filter_change", { filter: "documents", value: next });
                  }}
                  className="h-9 text-sm"
                >
                  <option value="any">Any</option>
                  <option value="documents">Has documents</option>
                  <option value="photos">Has photos</option>
                </Select>
              </div>
              {watchlist.size > 0 && (
                <button
                  type="button"
                  onClick={handleExportWatchlist}
                  className="text-xs font-medium text-cyan-800 hover:underline"
                >
                  Export watchlist CSV
                </button>
              )}
              {savedSearches.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
                  <span className="text-xs font-medium text-slate-600">Saved:</span>
                  {savedSearches.slice(0, 5).map((s) => (
                    <span key={s.id} className="inline-flex items-center gap-0.5">
                      <button
                        type="button"
                        onClick={() => applySavedSearch(s)}
                        className="rounded-full border border-violet-200/80 bg-violet-50/90 px-2.5 py-1 text-xs text-violet-900 hover:bg-violet-100"
                      >
                        {s.name}
                      </button>
                      <button
                        type="button"
                        onClick={() => setSavedSearches(deleteSavedSearch(s.id))}
                        className="rounded px-1 text-[10px] text-slate-500 hover:text-rose-700"
                        aria-label={`Delete saved search ${s.name}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-4 pb-10">
        {sorted.length > 0 && (
          <PaginationBar
            page={safePage}
            pageSize={pageSize}
            totalItems={sorted.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}

        {sorted.length === 0 ? (
          <div className="glass-panel space-y-4 py-12 text-center">
            <p className="text-slate-600">No auctions match your filters.</p>
            <button type="button" onClick={clearAllFilters} className="btn-glass-primary">
              Clear all filters
            </button>
          </div>
        ) : (
          paginated.map((auction, i) => (
            <AuctionCard
              key={auction.id}
              auction={auction}
              index={i}
              watched={isWatched(auction.id, watchlist)}
              onToggleWatch={handleToggleWatch}
            />
          ))
        )}

        {sorted.length > 0 && (
          <PaginationBar
            page={safePage}
            pageSize={pageSize}
            totalItems={sorted.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>
    </div>
  );
}
