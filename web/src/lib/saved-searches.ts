import type { SortOption, DatePreset } from "@/lib/auction-filters";

export interface SavedSearch {
  id: string;
  name: string;
  createdAt: string;
  query: string;
  sourceFilter: string;
  assetCategory: string;
  stateFilter: string;
  regionFilter: string;
  lotType: string;
  confidence: string;
  priceStatus: string;
  emdStatus: string;
  datePreset: DatePreset;
  customFrom: string;
  customTo: string;
  sortBy: SortOption;
  includeClosed: boolean;
  watchlistOnly: boolean;
}

const STORAGE_KEY = "mstc_auction_saved_searches_v1";

export function loadSavedSearches(): SavedSearch[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw) as SavedSearch[];
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function persistSavedSearches(searches: SavedSearch[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(searches));
}

export function deleteSavedSearch(id: string): SavedSearch[] {
  const next = loadSavedSearches().filter((s) => s.id !== id);
  persistSavedSearches(next);
  return next;
}

export function upsertSavedSearch(search: SavedSearch): SavedSearch[] {
  const existing = loadSavedSearches();
  const idx = existing.findIndex((s) => s.id === search.id);
  const next = [...existing];
  if (idx >= 0) next[idx] = search;
  else next.unshift(search);
  persistSavedSearches(next);
  return next;
}
