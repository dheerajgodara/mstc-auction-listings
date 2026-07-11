import {
  isActiveOrUpcoming,
  matchesCityFilter,
  matchesClosingDateFilter,
  matchesDisplayStateFilter,
  matchesDocumentsFilter,
  matchesImportedDateFilter,
  matchesLargeLotsOnly,
  matchesListedDateFilter,
  matchesMaterialCategoryFilter,
  matchesQuantityMinFilter,
  type DatePreset,
  type DocumentsFilter,
  type ImportedPreset,
  type ListedPreset,
  type QuantityMinFilter,
} from "@/lib/auction-filters";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import type { EmdParseStatus } from "@/types/auction";
import type { AuctionRecord } from "@/types/auction";
export type FacetKey =
  | "source"
  | "assetCategory"
  | "state"
  | "region"
  | "city"
  | "material"
  | "lotType"
  | "confidence"
  | "priceStatus"
  | "emdStatus"
  | "datePreset";
export interface DiscoveryFilters {
  sourceFilter: string;
  assetCategory: string;
  stateFilter: string;
  regionFilter: string;
  cityFilter: string;
  materialFilter: string;
  lotType: string;
  confidence: string;
  priceStatus: string;
  emdStatus: string;
  datePreset: DatePreset;
  customFrom: string;
  customTo: string;
  listedPreset: ListedPreset;
  listedFrom: string;
  listedTo: string;
  importedPreset: ImportedPreset;
  importedFrom: string;
  importedTo: string;
  quantityMin: QuantityMinFilter;
  largeLotsOnly: boolean;
  documentsFilter: DocumentsFilter;
  includeClosed: boolean;
  watchlistOnly: boolean;
  watchlist?: Set<string>;
}
export type FacetCounts = Record<FacetKey, Record<string, number>>;
function effectiveDatePreset(
  preset: DatePreset,
  customFrom: string,
  customTo: string,
): DatePreset {
  return preset === "all" && (customFrom || customTo) ? "custom" : preset;
}
function effectiveListedPreset(
  preset: ListedPreset,
  customFrom: string,
  customTo: string,
): ListedPreset {
  return preset === "all" && (customFrom || customTo) ? "custom" : preset;
}
function effectiveImportedPreset(
  preset: ImportedPreset,
  customFrom: string,
  customTo: string,
): ImportedPreset {
  return preset === "all" && (customFrom || customTo) ? "custom" : preset;
}
function matchesAuction(
  auction: AuctionRecord,
  filters: DiscoveryFilters,
  ignoreFacet?: FacetKey,
): boolean {
  if (filters.watchlistOnly && !filters.watchlist?.has(auction.id))
    return false;
  if (!filters.includeClosed && !isActiveOrUpcoming(auction.closing))
    return false;
  const auctionSource = auction.source ?? "mstc";
  if (ignoreFacet !== "source" && filters.sourceFilter !== "All") {
    if (auctionSource !== filters.sourceFilter) return false;
  }
  if (ignoreFacet !== "assetCategory" && filters.assetCategory !== "All") {
    if (auction.asset_category !== filters.assetCategory) return false;
  }
  if (
    ignoreFacet !== "state" &&
    !matchesDisplayStateFilter(auction, filters.stateFilter)
  ) {
    return false;
  }
  if (
    ignoreFacet !== "city" &&
    !matchesCityFilter(auction, filters.cityFilter)
  ) {
    return false;
  }
  if (
    ignoreFacet !== "material" &&
    !matchesMaterialCategoryFilter(auction, filters.materialFilter)
  ) {
    return false;
  }
  if (!matchesQuantityMinFilter(auction, filters.quantityMin)) return false;
  if (!matchesLargeLotsOnly(auction, filters.largeLotsOnly)) return false;
  if (!matchesDocumentsFilter(auction, filters.documentsFilter)) return false;
  if (ignoreFacet !== "region" && filters.regionFilter !== "All") {
    if (auction.region !== filters.regionFilter) return false;
  }
  if (ignoreFacet !== "lotType" && filters.lotType !== "All") {
    if (!auction.lot_types?.includes(filters.lotType)) return false;
  }
  if (ignoreFacet !== "confidence" && filters.confidence !== "All") {
    if (auction.parse_confidence !== filters.confidence) return false;
  }
  if (ignoreFacet !== "priceStatus" && filters.priceStatus !== "All") {
    if (auction.price_parse_status !== filters.priceStatus) return false;
  }
  if (ignoreFacet !== "emdStatus" && filters.emdStatus !== "All") {
    if (auction.emd_parse_status !== (filters.emdStatus as EmdParseStatus)) {
      return false;
    }
  }
  const closingPreset = effectiveDatePreset(
    filters.datePreset,
    filters.customFrom,
    filters.customTo,
  );
  if (
    ignoreFacet !== "datePreset" &&
    !matchesClosingDateFilter(
      auction.closing,
      closingPreset,
      filters.customFrom,
      filters.customTo,
    )
  ) {
    return false;
  }
  const listedPreset = effectiveListedPreset(
    filters.listedPreset,
    filters.listedFrom,
    filters.listedTo,
  );
  if (
    !matchesListedDateFilter(
      auction,
      listedPreset,
      filters.listedFrom,
      filters.listedTo,
    )
  ) {
    return false;
  }
  const importedPreset = effectiveImportedPreset(
    filters.importedPreset,
    filters.importedFrom,
    filters.importedTo,
  );
  if (
    !matchesImportedDateFilter(
      auction,
      importedPreset,
      filters.importedFrom,
      filters.importedTo,
    )
  ) {
    return false;
  }
  return true;
}
function increment(counts: Record<string, number>, key: string): void {
  counts[key] = (counts[key] ?? 0) + 1;
}
function countFacet(
  auctions: AuctionRecord[],
  filters: DiscoveryFilters,
  facet: FacetKey,
  assign: (auction: AuctionRecord, counts: Record<string, number>) => void,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const auction of auctions) {
    if (!matchesAuction(auction, filters, facet)) continue;
    assign(auction, counts);
  }
  return counts;
}
export function computeFacetCounts(
  auctions: AuctionRecord[],
  currentFilters: DiscoveryFilters,
): FacetCounts {
  return {
    source: countFacet(
      auctions,
      currentFilters,
      "source",
      (auction, counts) => {
        increment(counts, auction.source ?? "mstc");
      },
    ),
    assetCategory: countFacet(
      auctions,
      currentFilters,
      "assetCategory",
      (auction, counts) => {
        if (auction.asset_category) increment(counts, auction.asset_category);
      },
    ),
    state: countFacet(auctions, currentFilters, "state", (auction, counts) => {
      const display = enrichAuctionDisplay(auction);
      const state = display.display_location_state ?? auction.state;
      if (state) increment(counts, state);
    }),
    region: countFacet(
      auctions,
      currentFilters,
      "region",
      (auction, counts) => {
        if (auction.region) increment(counts, auction.region);
      },
    ),
    city: countFacet(auctions, currentFilters, "city", (auction, counts) => {
      const display = enrichAuctionDisplay(auction);
      if (display.display_location_city) {
        increment(counts, display.display_location_city);
      }
    }),
    material: countFacet(
      auctions,
      currentFilters,
      "material",
      (auction, counts) => {
        if (auction.display_material_category) {
          increment(counts, auction.display_material_category);
        }
      },
    ),
    lotType: countFacet(
      auctions,
      currentFilters,
      "lotType",
      (auction, counts) => {
        for (const lotType of auction.lot_types ?? []) {
          increment(counts, lotType);
        }
      },
    ),
    confidence: countFacet(
      auctions,
      currentFilters,
      "confidence",
      (auction, counts) => {
        if (auction.parse_confidence)
          increment(counts, auction.parse_confidence);
      },
    ),
    priceStatus: countFacet(
      auctions,
      currentFilters,
      "priceStatus",
      (auction, counts) => {
        if (auction.price_parse_status)
          increment(counts, auction.price_parse_status);
      },
    ),
    emdStatus: countFacet(
      auctions,
      currentFilters,
      "emdStatus",
      (auction, counts) => {
        if (auction.emd_parse_status)
          increment(counts, auction.emd_parse_status);
      },
    ),
    datePreset: countClosingDatePresetCounts(auctions, currentFilters),
  };
}
function countClosingDatePresetCounts(
  auctions: AuctionRecord[],
  filters: DiscoveryFilters,
): Record<string, number> {
  const presets: DatePreset[] = ["today", "tomorrow", "next3", "next7"];
  const counts: Record<string, number> = {};
  for (const preset of presets) {
    counts[preset] = 0;
  }
  for (const auction of auctions) {
    if (!matchesAuction(auction, filters, "datePreset")) continue;
    for (const preset of presets) {
      if (
        matchesClosingDateFilter(
          auction.closing,
          preset,
          filters.customFrom,
          filters.customTo,
        )
      ) {
        counts[preset] += 1;
      }
    }
  }
  return counts;
}
