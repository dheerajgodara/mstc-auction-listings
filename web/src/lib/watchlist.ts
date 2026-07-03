const STORAGE_KEY = "mstc_auction_watchlist_v1";

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
  const next = loadWatchlist();
  if (next.has(id)) next.delete(id);
  else next.add(id);
  saveWatchlist(next);
  return next;
}
