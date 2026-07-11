import type { DatePreset, SortOption } from "@/lib/auction-filters";
import {
  ASSET_CATEGORIES,
  type Density,
  SOURCES,
  type ViewMode,
} from "@/lib/discovery-constants";
export type { Density, ViewMode };
export interface DiscoveryUrlState {
  query: string;
  sourceFilter: string;
  assetCategory: string;
  stateFilter: string;
  regionFilter: string;
  cityFilter: string;
  materialFilter: string;
  sortBy: SortOption;
  datePreset: DatePreset;
  watchlistOnly: boolean;
  viewMode: ViewMode;
  density: Density;
}
export const DEFAULT_DISCOVERY_URL_STATE: DiscoveryUrlState = {
  query: "",
  sourceFilter: "All",
  assetCategory: "All",
  stateFilter: "All",
  regionFilter: "All",
  cityFilter: "All",
  materialFilter: "All",
  sortBy: "closing_asc",
  datePreset: "all",
  watchlistOnly: false,
  viewMode: "cards",
  density: "comfortable",
};
const SORT_OPTIONS: SortOption[] = [
  "closing_asc",
  "opening_asc",
  "price_asc",
  "price_desc",
  "best_opportunities",
  "listed_desc",
  "imported_desc",
  "quantity_desc",
  "lots_desc",
  "documents_desc",
  "distance_asc",
];
const DATE_PRESETS: DatePreset[] = [
  "all",
  "today",
  "tomorrow",
  "next3",
  "next7",
  "custom",
];
function isSourceFilter(value: string): boolean {
  return (SOURCES as readonly string[]).includes(value);
}
function isAssetCategory(value: string): boolean {
  return (ASSET_CATEGORIES as readonly string[]).includes(value);
}
function isSortOption(value: string): value is SortOption {
  return SORT_OPTIONS.includes(value as SortOption);
}
function isDatePreset(value: string): value is DatePreset {
  return DATE_PRESETS.includes(value as DatePreset);
}
function isViewMode(value: string): value is ViewMode {
  return value === "cards" || value === "table";
}
function isDensity(value: string): value is Density {
  return value === "comfortable" || value === "compact";
}
function parseBoolean(value: string | null): boolean {
  if (!value) return false;
  const normalized = value.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}
export function parseUrlState(search: string): DiscoveryUrlState {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  const next: DiscoveryUrlState = { ...DEFAULT_DISCOVERY_URL_STATE };
  const query = params.get("q") ?? params.get("query");
  if (query) next.query = query;
  const source = params.get("source") ?? params.get("sourceFilter");
  if (source && isSourceFilter(source)) next.sourceFilter = source;
  const category = params.get("category") ?? params.get("assetCategory");
  if (category && isAssetCategory(category)) next.assetCategory = category;
  const state = params.get("state") ?? params.get("stateFilter");
  if (state) next.stateFilter = state;
  const region = params.get("region") ?? params.get("regionFilter");
  if (region) next.regionFilter = region;
  const city = params.get("city") ?? params.get("cityFilter");
  if (city) next.cityFilter = city;
  const material = params.get("material") ?? params.get("materialFilter");
  if (material) next.materialFilter = material;
  const sort = params.get("sort") ?? params.get("sortBy");
  if (sort && isSortOption(sort)) next.sortBy = sort;
  const closing =
    params.get("closing") ?? params.get("date") ?? params.get("datePreset");
  if (closing && isDatePreset(closing)) next.datePreset = closing;
  const watchlist = params.get("watchlist") ?? params.get("watchlistOnly");
  if (watchlist != null) next.watchlistOnly = parseBoolean(watchlist);
  const view = params.get("view") ?? params.get("viewMode");
  if (view && isViewMode(view)) next.viewMode = view;
  const density = params.get("density");
  if (density && isDensity(density)) next.density = density;
  return next;
}
function appendIfDifferent(
  params: URLSearchParams,
  key: string,
  value: string,
  defaultValue: string,
): void {
  if (value !== defaultValue) params.set(key, value);
}
function appendBooleanIfTrue(
  params: URLSearchParams,
  key: string,
  value: boolean,
): void {
  if (value) params.set(key, "1");
}
export function buildUrlState(state: Partial<DiscoveryUrlState>): string {
  const merged: DiscoveryUrlState = {
    ...DEFAULT_DISCOVERY_URL_STATE,
    ...state,
  };
  const params = new URLSearchParams();
  if (merged.query.trim()) params.set("q", merged.query.trim());
  appendIfDifferent(params, "source", merged.sourceFilter, "All");
  appendIfDifferent(params, "category", merged.assetCategory, "All");
  appendIfDifferent(params, "state", merged.stateFilter, "All");
  appendIfDifferent(params, "region", merged.regionFilter, "All");
  appendIfDifferent(params, "city", merged.cityFilter, "All");
  appendIfDifferent(params, "material", merged.materialFilter, "All");
  appendIfDifferent(params, "sort", merged.sortBy, "closing_asc");
  appendIfDifferent(params, "closing", merged.datePreset, "all");
  appendBooleanIfTrue(params, "watchlist", merged.watchlistOnly);
  appendIfDifferent(params, "view", merged.viewMode, "cards");
  appendIfDifferent(params, "density", merged.density, "comfortable");
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}
export function readUrlStateFromWindow(): DiscoveryUrlState {
  if (typeof window === "undefined") return { ...DEFAULT_DISCOVERY_URL_STATE };
  return parseUrlState(window.location.search);
}
export function applyUrlStateToWindow(state: Partial<DiscoveryUrlState>): void {
  if (typeof window === "undefined") return;
  const search = buildUrlState(state);
  const url = `${window.location.pathname}${search}${window.location.hash}`;
  window.history.replaceState(null, "", url);
}
