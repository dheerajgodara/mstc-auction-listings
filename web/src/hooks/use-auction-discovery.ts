"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applySortOption,
  isActiveOrUpcoming,
  matchesCityFilter,
  matchesClosingDateFilter,
  matchesDisplayStateFilter,
  matchesDocumentsFilter,
  matchesEmdEligibleFilter,
  matchesGstFilter,
  matchesImportedDateFilter,
  matchesLargeLotsOnly,
  matchesListedDateFilter,
  matchesMaterialCategoryFilter,
  matchesMaterialTreeFilter,
  matchesQuantityMinFilter,
  matchesRadiusFilter,
  parseClosingMs,
  type DatePreset,
  type DocumentsFilter,
  type ImportedPreset,
  type ListedPreset,
  type QuantityMinFilter,
  type SortOption,
} from "@/lib/auction-filters";
import {
  ASSET_CATEGORIES,
  CONFIDENCE,
  EMD_STATUS,
  LOT_TYPES,
  PRICE_STATUS,
  SOURCES,
  type AssetCategoryFilter,
  type ConfidenceFilter,
  type Density,
  type EmdStatusFilter,
  type LotTypeFilter,
  type PriceStatusFilter,
  type SourceFilter,
  type ViewMode,
} from "@/lib/discovery-constants";
import { computeFacetCounts } from "@/lib/facet-counts";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { rankAuctionsBySearch } from "@/lib/search";
import {
  applyUrlStateToWindow,
  readUrlStateFromWindow,
  type DiscoveryUrlState,
} from "@/lib/url-state";
import { loadEmdBalance } from "@/lib/emd-calculator";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useUpgradePrompt } from "@/components/upgrade-prompt";
import { trackEvent, trackFilterChange } from "@/lib/analytics";
import {
  tryUpsertSavedSearch,
  type SavedSearch,
} from "@/lib/saved-searches";
import { loadWatchlist, tryToggleWatchlist } from "@/lib/watchlist";
import type { AuctionRecord, EmdParseStatus } from "@/types/auction";
const DENSITY_KEY = "auction_discovery_density";
const VIEW_KEY = "auction_discovery_view";
const PAGE_SIZE_KEY = "auction_discovery_page_size";
function loadPageSize(): number {
  if (typeof window === "undefined") return 50;
  const v = Number(localStorage.getItem(PAGE_SIZE_KEY));
  return v === 25 || v === 50 || v === 100 ? v : 50;
}
function loadDensity(): Density {
  if (typeof window === "undefined") return "comfortable";
  const v = localStorage.getItem(DENSITY_KEY);
  return v === "compact" ? "compact" : "comfortable";
}
function loadViewMode(): ViewMode {
  if (typeof window === "undefined") return "cards";
  const v = localStorage.getItem(VIEW_KEY);
  return v === "table" ? "table" : "cards";
}
export function useAuctionDiscovery(auctions: AuctionRecord[]) {
  const urlInit =
    typeof window !== "undefined" ? readUrlStateFromWindow() : null;
  const [query, setQuery] = useState(urlInit?.query ?? "");
  const debouncedQuery = useDebouncedValue(query, 200);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>(
    (urlInit?.sourceFilter as SourceFilter) ?? "All",
  );
  const [assetCategory, setAssetCategory] = useState<AssetCategoryFilter>(
    (urlInit?.assetCategory as AssetCategoryFilter) ?? "All",
  );
  const [stateFilter, setStateFilter] = useState(urlInit?.stateFilter ?? "All");
  const [regionFilter, setRegionFilter] = useState(
    urlInit?.regionFilter ?? "All",
  );
  const [cityFilter, setCityFilter] = useState(urlInit?.cityFilter ?? "All");
  const [materialFilter, setMaterialFilter] = useState(
    urlInit?.materialFilter ?? "All",
  );
  const [lotType, setLotType] = useState<LotTypeFilter>("All");
  const [confidence, setConfidence] = useState<ConfidenceFilter>("All");
  const [priceStatus, setPriceStatus] = useState<PriceStatusFilter>("All");
  const [emdStatus, setEmdStatus] = useState<EmdStatusFilter>("All");
  const [datePreset, setDatePreset] = useState<DatePreset>(
    urlInit?.datePreset ?? "all",
  );
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [listedPreset, setListedPreset] = useState<ListedPreset>("all");
  const [listedFrom, setListedFrom] = useState("");
  const [listedTo, setListedTo] = useState("");
  const [importedPreset, setImportedPreset] = useState<ImportedPreset>("all");
  const [importedFrom, setImportedFrom] = useState("");
  const [importedTo, setImportedTo] = useState("");
  const [quantityMin, setQuantityMin] = useState<QuantityMinFilter>("any");
  const [largeLotsOnly, setLargeLotsOnly] = useState(false);
  const [documentsFilter, setDocumentsFilter] =
    useState<DocumentsFilter>("any");
  const [sortBy, setSortBy] = useState<SortOption>(
    urlInit?.sortBy ?? "closing_asc",
  );
  const [includeClosed, setIncludeClosed] = useState(true);
  const [watchlistOnly, setWatchlistOnly] = useState(
    urlInit?.watchlistOnly ?? false,
  );
  const [filtersOpen, setFiltersOpen] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState(50);
  const [watchlist, setWatchlist] = useState<Set<string>>(() => new Set());
  const [pinCode, setPinCode] = useState("");
  const [radiusKm, setRadiusKm] = useState(0);
  const [emdEligibleOnly, setEmdEligibleOnly] = useState(false);
  const [gstFilter, setGstFilter] = useState("all");
  const [materialTreeIds, setMaterialTreeIds] = useState<Set<string>>(
    new Set(),
  );
  const [density, setDensityState] = useState<Density>(
    urlInit?.density ?? "comfortable",
  );
  const [viewMode, setViewModeState] = useState<ViewMode>(
    urlInit?.viewMode ?? "cards",
  );
  useEffect(() => {
    setDensityState(loadDensity());
    setViewModeState(loadViewMode());
    setPageSizeState(loadPageSize());
    setWatchlist(loadWatchlist());
    if (loadEmdBalance() > 0) setEmdEligibleOnly(true);
  }, []);
  const { gateFeature } = useUpgradePrompt();
  const onToggleWatch = useCallback(
    (id: string) => {
      const result = tryToggleWatchlist(id);
      if (!result.ok) {
        gateFeature("watchlist_add", false, "watchlist_toggle");
        return;
      }
      setWatchlist(result.watchlist);
    },
    [gateFeature],
  );
  const setPageSize = useCallback((size: number) => {
    setPageSizeState(size);
    localStorage.setItem(PAGE_SIZE_KEY, String(size));
  }, []);
  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    localStorage.setItem(DENSITY_KEY, d);
  }, []);
  const setViewMode = useCallback((v: ViewMode) => {
    setViewModeState(v);
    localStorage.setItem(VIEW_KEY, v);
  }, []);
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
    listedPreset === "all" && (listedFrom || listedTo)
      ? "custom"
      : listedPreset;
  const effectiveImportedPreset =
    importedPreset === "all" && (importedFrom || importedTo)
      ? "custom"
      : importedPreset;
  const materialTreeKey = [...materialTreeIds].sort().join(",");
  const filtered = useMemo(() => {
    return auctions.filter((a) => {
      if (!includeClosed && !isActiveOrUpcoming(a.closing)) return false;
      const auctionSource = a.source ?? "mstc";
      if (sourceFilter !== "All" && auctionSource !== sourceFilter)
        return false;
      if (assetCategory !== "All" && a.asset_category !== assetCategory)
        return false;
      if (!matchesDisplayStateFilter(a, stateFilter)) return false;
      if (!matchesCityFilter(a, cityFilter)) return false;
      if (!matchesMaterialCategoryFilter(a, materialFilter)) return false;
      if (!matchesQuantityMinFilter(a, quantityMin)) return false;
      if (!matchesLargeLotsOnly(a, largeLotsOnly)) return false;
      if (!matchesDocumentsFilter(a, documentsFilter)) return false;
      if (regionFilter !== "All" && a.region !== regionFilter) return false;
      if (lotType !== "All" && !a.lot_types?.includes(lotType)) return false;
      if (confidence !== "All" && a.parse_confidence !== confidence)
        return false;
      if (priceStatus !== "All" && a.price_parse_status !== priceStatus)
        return false;
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
      if (!matchesRadiusFilter(a, pinCode, radiusKm)) return false;
      if (emdEligibleOnly && !matchesEmdEligibleFilter(a, loadEmdBalance()))
        return false;
      if (!matchesGstFilter(a, gstFilter)) return false;
      if (!matchesMaterialTreeFilter(a, materialTreeIds)) return false;
      if (watchlistOnly && !watchlist.has(a.id)) return false;
      return true;
    });
  }, [
    auctions,
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
    pinCode,
    radiusKm,
    emdEligibleOnly,
    gstFilter,
    materialTreeKey,
    watchlistOnly,
    watchlist,
  ]);
  const sorted = useMemo(() => {
    const base = debouncedQuery.trim()
      ? rankAuctionsBySearch(filtered, debouncedQuery)
      : filtered;
    return applySortOption(base, sortBy, pinCode);
  }, [filtered, debouncedQuery, sortBy, pinCode]);
  const facetCounts = useMemo(
    () =>
      computeFacetCounts(auctions, {
        sourceFilter,
        assetCategory,
        stateFilter,
        regionFilter,
        cityFilter,
        materialFilter,
        lotType,
        confidence,
        priceStatus,
        emdStatus,
        datePreset: effectiveDatePreset,
        customFrom,
        customTo,
        listedPreset: effectiveListedPreset,
        listedFrom,
        listedTo,
        importedPreset: effectiveImportedPreset,
        importedFrom,
        importedTo,
        quantityMin,
        largeLotsOnly,
        documentsFilter,
        includeClosed,
        watchlistOnly: false,
      }),
    [
      auctions,
      debouncedQuery,
      sourceFilter,
      assetCategory,
      stateFilter,
      regionFilter,
      cityFilter,
      materialFilter,
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
      quantityMin,
      largeLotsOnly,
      documentsFilter,
      includeClosed,
    ],
  );
  const urlSlice: DiscoveryUrlState = useMemo(
    () => ({
      query,
      sourceFilter,
      assetCategory,
      stateFilter,
      regionFilter,
      cityFilter,
      materialFilter,
      sortBy,
      datePreset,
      watchlistOnly,
      viewMode,
      density,
    }),
    [
      query,
      sourceFilter,
      assetCategory,
      stateFilter,
      regionFilter,
      cityFilter,
      materialFilter,
      sortBy,
      datePreset,
      watchlistOnly,
      viewMode,
      density,
    ],
  );
  useEffect(() => {
    applyUrlStateToWindow(urlSlice);
  }, [urlSlice]);
  const applySavedSearch = useCallback((saved: SavedSearch) => {
    setQuery(saved.query);
    setSourceFilter(saved.sourceFilter as SourceFilter);
    setAssetCategory(saved.assetCategory as AssetCategoryFilter);
    setStateFilter(saved.stateFilter);
    setRegionFilter(saved.regionFilter);
    setLotType(saved.lotType as LotTypeFilter);
    setConfidence(saved.confidence as ConfidenceFilter);
    setPriceStatus(saved.priceStatus as PriceStatusFilter);
    setEmdStatus(saved.emdStatus as EmdStatusFilter);
    setDatePreset(saved.datePreset);
    setCustomFrom(saved.customFrom);
    setCustomTo(saved.customTo);
    setListedPreset(saved.listedPreset ?? "all");
    setListedFrom(saved.listedFrom ?? "");
    setListedTo(saved.listedTo ?? "");
    setSortBy(saved.sortBy);
    setIncludeClosed(saved.includeClosed);
    setWatchlistOnly(saved.watchlistOnly);
  }, []);
  const clearAllFilters = useCallback(() => {
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
    setDocumentsFilter("any");
    setIncludeClosed(true);
    setWatchlistOnly(false);
    setPinCode("");
    setRadiusKm(0);
    setEmdEligibleOnly(false);
    setGstFilter("all");
    setMaterialTreeIds(new Set());
  }, []);
  const saveCurrentSearch = useCallback(() => {
    const name =
      query.trim() ||
      [sourceFilter !== "All" ? sourceFilter : "", stateFilter !== "All" ? stateFilter : ""]
        .filter(Boolean)
        .join(" · ") ||
      "Saved search";
    const search: SavedSearch = {
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
    const result = tryUpsertSavedSearch(search);
    if (!result.ok) {
      gateFeature("saved_search_save", false, "discovery_save");
      return false;
    }
    trackEvent("saved_search_save", { saved_count: result.searches.length });
    return true;
  }, [
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
    gateFeature,
  ]);
  const filterValues = {
    sourceFilter,
    assetCategory,
    stateFilter,
    regionFilter,
    cityFilter,
    materialFilter,
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
    quantityMin,
    largeLotsOnly,
    documentsFilter,
    includeClosed,
    watchlistOnly,
    pinCode,
    radiusKm,
    emdEligibleOnly,
    gstFilter,
    materialTreeIds,
  };
  const filterSetters = {
    setSourceFilter,
    setAssetCategory,
    setStateFilter,
    setRegionFilter,
    setCityFilter,
    setMaterialFilter,
    setLotType,
    setConfidence,
    setPriceStatus,
    setEmdStatus,
    setDatePreset,
    setCustomFrom,
    setCustomTo,
    setListedPreset,
    setListedFrom,
    setListedTo,
    setImportedPreset,
    setImportedFrom,
    setImportedTo,
    setQuantityMin,
    setLargeLotsOnly,
    setDocumentsFilter,
    setIncludeClosed,
    setWatchlistOnly,
    setPinCode,
    setRadiusKm,
    setEmdEligibleOnly,
    setGstFilter,
    setMaterialTreeIds,
  };
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
  const useVirtualList = process.env.NEXT_PUBLIC_VIRTUAL_LIST === "1";
  const nextClosingMs = useMemo(() => {
    const now = Date.now();
    let best: number | null = null;
    for (const a of sorted) {
      const ms = parseClosingMs(a.closing);
      if (ms !== null && ms > now && (best === null || ms < best)) best = ms;
    }
    return best;
  }, [sorted]);

  const filterSignature = useMemo(
    () =>
      [
        sourceFilter,
        assetCategory,
        stateFilter,
        regionFilter,
        cityFilter,
        materialFilter,
        lotType,
        confidence,
        priceStatus,
        emdStatus,
        effectiveDatePreset,
        customFrom,
        customTo,
        effectiveListedPreset,
        effectiveImportedPreset,
        quantityMin,
        largeLotsOnly,
        documentsFilter,
        includeClosed,
        watchlistOnly,
        pinCode,
        radiusKm,
        emdEligibleOnly,
        gstFilter,
        materialTreeKey,
      ].join("|"),
    [
      sourceFilter,
      assetCategory,
      stateFilter,
      regionFilter,
      cityFilter,
      materialFilter,
      lotType,
      confidence,
      priceStatus,
      emdStatus,
      effectiveDatePreset,
      customFrom,
      customTo,
      effectiveListedPreset,
      effectiveImportedPreset,
      quantityMin,
      largeLotsOnly,
      documentsFilter,
      includeClosed,
      watchlistOnly,
      pinCode,
      radiusKm,
      emdEligibleOnly,
      gstFilter,
      materialTreeKey,
    ],
  );
  const filterSigBoot = useRef(true);
  useEffect(() => {
    if (filterSigBoot.current) {
      filterSigBoot.current = false;
      return;
    }
    const activeCount = filterSignature.split("|").filter((v) => v && v !== "All" && v !== "all" && v !== "any" && v !== "false" && v !== "0" && v !== "").length;
    trackFilterChange(activeCount);
  }, [filterSignature]);
  useEffect(() => {
    if (typeof requestIdleCallback === "undefined") return;
    const nextPage = safePage + 1;
    if (nextPage > totalPages) return;
    const id = requestIdleCallback(() => {
      const start = (nextPage - 1) * pageSize;
      sorted.slice(start, start + pageSize);
    });
    return () => cancelIdleCallback(id);
  }, [safePage, totalPages, pageSize, sorted]);
  return {
    query,
    setQuery,
    debouncedQuery,
    sortBy,
    setSortBy,
    density,
    setDensity,
    viewMode,
    setViewMode,
    filtersOpen,
    setFiltersOpen,
    page,
    setPage,
    pageSize,
    setPageSize,
    safePage,
    totalPages,
    paginated,
    sorted,
    filtered,
    facetCounts,
    filterValues,
    filterSetters,
    clearAllFilters,
    regions,
    states,
    cities,
    effectiveDatePreset,
    effectiveListedPreset,
    effectiveImportedPreset,
    useVirtualList,
    SOURCES,
    ASSET_CATEGORIES,
    LOT_TYPES,
    CONFIDENCE,
    PRICE_STATUS,
    EMD_STATUS,
    nextClosingMs,
    watchlist,
    onToggleWatch,
    applySavedSearch,
    saveCurrentSearch,
  };
}
