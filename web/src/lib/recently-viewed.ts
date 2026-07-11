const STORAGE_KEY = "mstc_auction_recently_viewed_v1";
const MAX_ENTRIES = 20;
export interface RecentlyViewedEntry {
  id: string;
  viewedAt: string;
}
function readEntries(): RecentlyViewedEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw) as RecentlyViewedEntry[];
    if (!Array.isArray(data)) return [];
    return data.filter(
      (entry): entry is RecentlyViewedEntry =>
        typeof entry?.id === "string" && typeof entry?.viewedAt === "string",
    );
  } catch {
    return [];
  }
}
function writeEntries(entries: RecentlyViewedEntry[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(entries.slice(0, MAX_ENTRIES)),
  );
}
export function getRecentlyViewed(): RecentlyViewedEntry[] {
  return readEntries();
}
export function addRecentlyViewed(id: string): RecentlyViewedEntry[] {
  const trimmed = id.trim();
  if (!trimmed) return readEntries();
  const now = new Date().toISOString();
  const without = readEntries().filter((entry) => entry.id !== trimmed);
  const next = [{ id: trimmed, viewedAt: now }, ...without].slice(
    0,
    MAX_ENTRIES,
  );
  writeEntries(next);
  return next;
}
export function clearRecentlyViewed(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}
