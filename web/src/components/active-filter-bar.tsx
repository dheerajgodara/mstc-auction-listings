"use client";
import { X } from "lucide-react";
import {
  isDateFilterActive,
  isImportedFilterActive,
  isListedFilterActive,
  type DatePreset,
  type DocumentsFilter,
  type ImportedPreset,
  type ListedPreset,
  type QuantityMinFilter,
} from "@/lib/auction-filters";
import {
  DATE_PRESET_LABELS,
  IMPORTED_PRESET_LABELS,
  LISTED_PRESET_LABELS,
  categoryLabel,
  sourceLabel,
  type AssetCategoryFilter,
  type ConfidenceFilter,
  type EmdStatusFilter,
  type LotTypeFilter,
  type PriceStatusFilter,
  type SourceFilter,
} from "@/lib/discovery-constants";
import { materialCategoryLabel } from "@/lib/display-enrichment";
import { cn } from "@/lib/utils";
export interface ActiveFilterChip {
  key: string;
  label: string;
  onRemove: () => void;
}
function RemovableChip({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onRemove}
      className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted/80 focus-visible:outline-none focus-ring"
    >
      {" "}
      {label} <X className="h-3 w-3" />{" "}
    </button>
  );
}
export function buildActiveFilterChips(input: {
  query?: string;
  setQuery?: (v: string) => void;
  sourceFilter: SourceFilter;
  setSourceFilter: (v: SourceFilter) => void;
  assetCategory: AssetCategoryFilter;
  setAssetCategory: (v: AssetCategoryFilter) => void;
  stateFilter: string;
  setStateFilter: (v: string) => void;
  regionFilter: string;
  setRegionFilter: (v: string) => void;
  cityFilter: string;
  setCityFilter: (v: string) => void;
  materialFilter: string;
  setMaterialFilter: (v: string) => void;
  lotType: LotTypeFilter;
  setLotType: (v: LotTypeFilter) => void;
  confidence: ConfidenceFilter;
  setConfidence: (v: ConfidenceFilter) => void;
  priceStatus: PriceStatusFilter;
  setPriceStatus: (v: PriceStatusFilter) => void;
  emdStatus: EmdStatusFilter;
  setEmdStatus: (v: EmdStatusFilter) => void;
  datePreset: DatePreset;
  setDatePreset: (v: DatePreset) => void;
  customFrom: string;
  setCustomFrom: (v: string) => void;
  customTo: string;
  setCustomTo: (v: string) => void;
  listedPreset: ListedPreset;
  setListedPreset: (v: ListedPreset) => void;
  listedFrom: string;
  setListedFrom: (v: string) => void;
  listedTo: string;
  setListedTo: (v: string) => void;
  importedPreset: ImportedPreset;
  setImportedPreset: (v: ImportedPreset) => void;
  importedFrom: string;
  setImportedFrom: (v: string) => void;
  importedTo: string;
  setImportedTo: (v: string) => void;
  quantityMin: QuantityMinFilter;
  setQuantityMin: (v: QuantityMinFilter) => void;
  largeLotsOnly: boolean;
  setLargeLotsOnly: (v: boolean) => void;
  documentsFilter: DocumentsFilter;
  setDocumentsFilter: (v: DocumentsFilter) => void;
  includeClosed: boolean;
  setIncludeClosed: (v: boolean) => void;
  watchlistOnly?: boolean;
  setWatchlistOnly?: (v: boolean) => void;
}): ActiveFilterChip[] {
  const effectiveDatePreset =
    input.datePreset === "all" && (input.customFrom || input.customTo)
      ? "custom"
      : input.datePreset;
  const effectiveListedPreset =
    input.listedPreset === "all" && (input.listedFrom || input.listedTo)
      ? "custom"
      : input.listedPreset;
  const effectiveImportedPreset =
    input.importedPreset === "all" && (input.importedFrom || input.importedTo)
      ? "custom"
      : input.importedPreset;
  const chips: ActiveFilterChip[] = [];
  if (input.query?.trim() && input.setQuery) {
    chips.push({
      key: "search",
      label: `Search: ${input.query.trim()}`,
      onRemove: () => input.setQuery!(""),
    });
  }
  if (
    isDateFilterActive(effectiveDatePreset, input.customFrom, input.customTo)
  ) {
    chips.push({
      key: "date",
      label:
        effectiveDatePreset === "custom"
          ? `Dates: ${input.customFrom || "…"} – ${input.customTo || "…"}`
          : DATE_PRESET_LABELS[effectiveDatePreset],
      onRemove: () => {
        input.setDatePreset("all");
        input.setCustomFrom("");
        input.setCustomTo("");
      },
    });
  }
  if (
    isListedFilterActive(
      effectiveListedPreset,
      input.listedFrom,
      input.listedTo,
    )
  ) {
    chips.push({
      key: "listed",
      label:
        effectiveListedPreset === "custom"
          ? `Listed: ${input.listedFrom || "…"} – ${input.listedTo || "…"}`
          : LISTED_PRESET_LABELS[effectiveListedPreset],
      onRemove: () => {
        input.setListedPreset("all");
        input.setListedFrom("");
        input.setListedTo("");
      },
    });
  }
  if (
    isImportedFilterActive(
      effectiveImportedPreset,
      input.importedFrom,
      input.importedTo,
    )
  ) {
    chips.push({
      key: "imported",
      label:
        effectiveImportedPreset === "custom"
          ? `Imported: ${input.importedFrom || "…"} – ${input.importedTo || "…"}`
          : IMPORTED_PRESET_LABELS[effectiveImportedPreset],
      onRemove: () => {
        input.setImportedPreset("all");
        input.setImportedFrom("");
        input.setImportedTo("");
      },
    });
  }
  if (input.sourceFilter !== "All") {
    chips.push({
      key: "source",
      label: `Source: ${sourceLabel(input.sourceFilter)}`,
      onRemove: () => input.setSourceFilter("All"),
    });
  }
  if (input.assetCategory !== "All") {
    chips.push({
      key: "category",
      label: `Category: ${categoryLabel(input.assetCategory)}`,
      onRemove: () => input.setAssetCategory("All"),
    });
  }
  if (input.stateFilter !== "All") {
    chips.push({
      key: "state",
      label: `State: ${input.stateFilter}`,
      onRemove: () => input.setStateFilter("All"),
    });
  }
  if (input.cityFilter !== "All") {
    chips.push({
      key: "city",
      label: `City: ${input.cityFilter}`,
      onRemove: () => input.setCityFilter("All"),
    });
  }
  if (input.materialFilter !== "All") {
    chips.push({
      key: "material",
      label: `Material: ${materialCategoryLabel(input.materialFilter) ?? input.materialFilter}`,
      onRemove: () => input.setMaterialFilter("All"),
    });
  }
  if (input.quantityMin !== "any") {
    chips.push({
      key: "quantity",
      label: `Quantity: ${input.quantityMin}+ MT`,
      onRemove: () => input.setQuantityMin("any"),
    });
  }
  if (input.largeLotsOnly) {
    chips.push({
      key: "largeLots",
      label: "Large lots (100+ MT)",
      onRemove: () => input.setLargeLotsOnly(false),
    });
  }
  if (input.documentsFilter === "documents") {
    chips.push({
      key: "documents",
      label: "Has documents",
      onRemove: () => input.setDocumentsFilter("any"),
    });
  }
  if (input.documentsFilter === "photos") {
    chips.push({
      key: "photos",
      label: "Has photos",
      onRemove: () => input.setDocumentsFilter("any"),
    });
  }
  if (input.regionFilter !== "All") {
    chips.push({
      key: "region",
      label: `Region: ${input.regionFilter}`,
      onRemove: () => input.setRegionFilter("All"),
    });
  }
  if (input.confidence !== "All") {
    chips.push({
      key: "confidence",
      label: `Confidence: ${input.confidence}`,
      onRemove: () => input.setConfidence("All"),
    });
  }
  if (input.priceStatus !== "All") {
    chips.push({
      key: "price",
      label: `Price: ${input.priceStatus.replace(/_/g, " ")}`,
      onRemove: () => input.setPriceStatus("All"),
    });
  }
  if (input.emdStatus !== "All") {
    chips.push({
      key: "emd",
      label: `EMD: ${input.emdStatus.replace(/_/g, " ")}`,
      onRemove: () => input.setEmdStatus("All"),
    });
  }
  if (input.lotType !== "All") {
    chips.push({
      key: "lotType",
      label: `Type: ${input.lotType}`,
      onRemove: () => input.setLotType("All"),
    });
  }
  if (!input.includeClosed) {
    chips.push({
      key: "closed",
      label: "Active/upcoming only",
      onRemove: () => input.setIncludeClosed(true),
    });
  }
  if (input.watchlistOnly && input.setWatchlistOnly) {
    chips.push({
      key: "watchlist",
      label: "Watchlist only",
      onRemove: () => input.setWatchlistOnly!(false),
    });
  }
  return chips;
}
export function ActiveFilterBar({
  chips,
  onClearAll,
  className,
}: {
  chips: ActiveFilterChip[];
  onClearAll: () => void;
  className?: string;
}) {
  if (chips.length === 0) return null;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 border-t border-border pt-2",
        className,
      )}
      role="list"
      aria-label="Active filters"
    >
      {" "}
      {chips.map((chip) => (
        <RemovableChip
          key={chip.key}
          label={chip.label}
          onRemove={chip.onRemove}
        />
      ))}{" "}
      <button
        type="button"
        onClick={onClearAll}
        className="text-xs font-medium link-action focus-visible:outline-none focus-visible:ring-2 focus-ring"
      >
        {" "}
        Clear all{" "}
      </button>{" "}
    </div>
  );
}
