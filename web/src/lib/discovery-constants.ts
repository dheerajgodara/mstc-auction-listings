import type {
  DatePreset,
  DocumentsFilter,
  ImportedPreset,
  ListedPreset,
  QuantityMinFilter,
  SortOption,
} from "@/lib/auction-filters";
import type { AssetCategory, AuctionSource } from "@/types/auction";
export const SOURCES = ["All", "mstc", "eauction", "gem_forward"] as const;
export type SourceFilter = (typeof SOURCES)[number];
export const ASSET_CATEGORIES = [
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
export type AssetCategoryFilter = (typeof ASSET_CATEGORIES)[number];
export const LOT_TYPES = ["All", "General", "RVSF", "Hazardous"] as const;
export type LotTypeFilter = (typeof LOT_TYPES)[number];
export const CONFIDENCE = ["All", "high", "medium", "low", "minimal"] as const;
export type ConfidenceFilter = (typeof CONFIDENCE)[number];
export const PRICE_STATUS = [
  "All",
  "numeric",
  "range",
  "percentage_based",
  "not_disclosed",
  "missing",
] as const;
export type PriceStatusFilter = (typeof PRICE_STATUS)[number];
export const EMD_STATUS = [
  "All",
  "auction_wise",
  "item_wise",
  "not_required",
  "missing",
  "unknown",
] as const;
export type EmdStatusFilter = (typeof EMD_STATUS)[number];
export const SOURCE_LABELS: Record<AuctionSource, string> = {
  mstc: "MSTC",
  eauction: "eAuction",
  gem_forward: "GeM Forward",
};
export function sourceLabel(
  source?: AuctionSource | SourceFilter | null,
): string {
  if (!source || source === "All" || source === "mstc") return "MSTC";
  return SOURCE_LABELS[source as AuctionSource] ?? source;
}
export function categoryLabel(
  category: AssetCategory | AssetCategoryFilter,
): string {
  if (category === "All") return "All categories";
  return category.charAt(0).toUpperCase() + category.slice(1);
}
export const DATE_PRESETS: { id: DatePreset; label: string }[] = [
  { id: "today", label: "Closing today" },
  { id: "tomorrow", label: "Closing tomorrow" },
  { id: "next3", label: "Next 3 days" },
  { id: "next7", label: "Next 7 days" },
];
export const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  all: "All dates",
  today: "Closing today",
  tomorrow: "Closing tomorrow",
  next3: "Next 3 days",
  next7: "Next 7 days",
  custom: "Custom range",
};
export const LISTED_PRESETS: { id: ListedPreset; label: string }[] = [
  { id: "today", label: "Listed today" },
  { id: "yesterday", label: "Listed yesterday" },
  { id: "last3", label: "Last 3 days" },
  { id: "last7", label: "Last 7 days" },
  { id: "last14", label: "Last 14 days" },
];
export const LISTED_PRESET_LABELS: Record<ListedPreset, string> = {
  all: "All listing dates",
  today: "Listed today",
  yesterday: "Listed yesterday",
  last3: "Listed last 3 days",
  last7: "Listed last 7 days",
  last14: "Listed last 14 days",
  custom: "Custom range",
};
export const IMPORTED_PRESETS: { id: ImportedPreset; label: string }[] = [
  { id: "today", label: "Imported today" },
  { id: "yesterday", label: "Imported yesterday" },
  { id: "last3", label: "Last 3 days" },
  { id: "last7", label: "Last 7 days" },
];
export const IMPORTED_PRESET_LABELS: Record<ImportedPreset, string> = {
  all: "All import dates",
  today: "Imported today",
  yesterday: "Imported yesterday",
  last3: "Imported last 3 days",
  last7: "Imported last 7 days",
  custom: "Custom range",
};
export const QUANTITY_MIN_OPTIONS: { id: QuantityMinFilter; label: string }[] =
  [
    { id: "any", label: "Any quantity" },
    { id: "10", label: "10+ MT" },
    { id: "50", label: "50+ MT" },
    { id: "100", label: "100+ MT" },
    { id: "500", label: "500+ MT" },
    { id: "1000", label: "1000+ MT" },
  ];
export const DOCUMENTS_FILTER_OPTIONS: {
  id: DocumentsFilter;
  label: string;
}[] = [
  { id: "any", label: "Any" },
  { id: "documents", label: "Has documents" },
  { id: "photos", label: "Has photos" },
];
export const SORT_OPTIONS: { id: SortOption; label: string }[] = [
  { id: "closing_asc", label: "Closing soonest" },
  { id: "opening_asc", label: "Opening soonest" },
  { id: "listed_desc", label: "Recently listed" },
  { id: "imported_desc", label: "Recently imported" },
  { id: "quantity_desc", label: "Largest quantity" },
  { id: "lots_desc", label: "Most lots" },
  { id: "documents_desc", label: "Most documents" },
  { id: "price_asc", label: "Price low → high" },
  { id: "price_desc", label: "Price high → low" },
  { id: "best_opportunities", label: "Best opportunities" },
  { id: "distance_asc", label: "Nearest to PIN" },
];
export type ViewMode = "cards" | "table";
export type Density = "comfortable" | "compact";
export const VIEW_MODE_OPTIONS: { id: ViewMode; label: string }[] = [
  { id: "cards", label: "Cards" },
  { id: "table", label: "Grid" },
];
export const DENSITY_OPTIONS: { id: Density; label: string }[] = [
  { id: "comfortable", label: "Comfortable" },
  { id: "compact", label: "Compact" },
];
