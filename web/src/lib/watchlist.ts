import { canAddWatchlist } from "@/lib/entitlements";

const STORAGE_KEY = "mstc_auction_watchlist_v1";

export type WatchlistToggleResult =
  | { ok: true; watchlist: Set<string>; added: boolean }
  | { ok: false; reason: "cap_reached" };

export function loadWatchlist(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const ids = JSON.parse(raw) as string[];
    return new Set(Array.isArray(ids) ? ids : []);
  } catch {
    return new Set();
  }
}

export function saveWatchlist(ids: Set<string>): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
}

export function isWatched(id: string, watchlist?: Set<string>): boolean {
  return (watchlist ?? loadWatchlist()).has(id);
}

export function toggleWatchlist(id: string): Set<string> {
  const result = tryToggleWatchlist(id);
  return result.ok ? result.watchlist : loadWatchlist();
}

export function tryToggleWatchlist(id: string): WatchlistToggleResult {
  const next = loadWatchlist();
  if (next.has(id)) {
    next.delete(id);
    saveWatchlist(next);
    return { ok: true, watchlist: next, added: false };
  }
  if (!canAddWatchlist(next.size)) {
    return { ok: false, reason: "cap_reached" };
  }
  next.add(id);
  saveWatchlist(next);
  return { ok: true, watchlist: next, added: true };
}
