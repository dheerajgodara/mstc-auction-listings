export interface ChangelogEntry {
  version: string;
  date: string;
  title: string;
  items: string[];
}
export const CHANGELOG: ChangelogEntry[] = [
  {
    version: "0.2.0",
    date: "2026-07-06",
    title: "Discovery experience uplift",
    items: [
      "Shareable URL filter state for team workflows",
      "Facet counts on filter options",
      "Recently viewed auctions rail",
      "Private notes per auction",
      "Calendar export for closing times",
      "Geo radius filtering from city centroids",
    ],
  },
  {
    version: "0.1.0",
    date: "2026-03-01",
    title: "Initial public release",
    items: [
      "Multi-source auction listings from MSTC, GeM Forward, and eAuction",
      "Search, filters, and watchlist",
      "Lot details, documents, and import status page",
    ],
  },
];
const STORAGE_KEY = "mstc_auction_changelog_seen_v1";
function readSeenVersion(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
export function latestChangelogVersion(): string | null {
  return CHANGELOG[0]?.version ?? null;
}
export function getChangelogEntry(version: string): ChangelogEntry | undefined {
  return CHANGELOG.find((entry) => entry.version === version);
}
export function shouldShowChangelog(): boolean {
  const latest = latestChangelogVersion();
  if (!latest) return false;
  return readSeenVersion() !== latest;
}
export function markChangelogSeen(version?: string): void {
  if (typeof window === "undefined") return;
  const target = version ?? latestChangelogVersion();
  if (!target) return;
  localStorage.setItem(STORAGE_KEY, target);
}
export function resetChangelogSeen(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}
