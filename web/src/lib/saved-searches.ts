import { canSaveSearch } from "@/lib/entitlements";
import type {
  SortOption,
  DatePreset,
  ListedPreset,
} from "@/lib/auction-filters";

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
  listedPreset?: ListedPreset;
  listedFrom?: string;
  listedTo?: string;
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
  if (idx < 0) {
    const gate = canSaveNewSearch(existing.length);
    if (!gate.ok) return existing;
  }
  const next = [...existing];
  if (idx >= 0) next[idx] = search;
  else next.unshift(search);
  persistSavedSearches(next);
  return next;
}

export type SavedSearchSaveResult =
  | { ok: true; searches: SavedSearch[] }
  | { ok: false; reason: "cap_reached" };

export function tryUpsertSavedSearch(search: SavedSearch): SavedSearchSaveResult {
  const existing = loadSavedSearches();
  const idx = existing.findIndex((s) => s.id === search.id);
  if (idx < 0) {
    const gate = canSaveNewSearch(existing.length);
    if (!gate.ok) return { ok: false, reason: "cap_reached" };
  }
  return { ok: true, searches: upsertSavedSearch(search) };
}

function canSaveNewSearch(currentCount: number): { ok: boolean } {
  return { ok: canSaveSearch(currentCount) };
}
