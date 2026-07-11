"use client";
import {
  Calendar,
  MapPin,
  Package,
  Shield,
  Sparkles,
  Store,
} from "lucide-react";
import { FilterBottomSheet } from "@/components/filter-bottom-sheet";
import { Input, Select } from "@/components/ui/primitives";
import { useUpgradePrompt } from "@/components/upgrade-prompt";
import { canUsePremiumFeature } from "@/lib/entitlements";
import type {
  DatePreset,
  DocumentsFilter,
  ImportedPreset,
  ListedPreset,
  QuantityMinFilter,
} from "@/lib/auction-filters";
import {
  ASSET_CATEGORIES,
  CONFIDENCE,
  DATE_PRESETS,
  DATE_PRESET_LABELS,
  DOCUMENTS_FILTER_OPTIONS,
  EMD_STATUS,
  IMPORTED_PRESETS,
  IMPORTED_PRESET_LABELS,
  LISTED_PRESETS,
  LISTED_PRESET_LABELS,
  LOT_TYPES,
  PRICE_STATUS,
  QUANTITY_MIN_OPTIONS,
  SOURCES,
  categoryLabel,
  sourceLabel,
  type AssetCategoryFilter,
  type ConfidenceFilter,
  type EmdStatusFilter,
  type LotTypeFilter,
  type PriceStatusFilter,
  type SourceFilter,
} from "@/lib/discovery-constants";
import { DISPLAY_MATERIAL_CATEGORIES } from "@/lib/display-enrichment";
import type { FacetCounts } from "@/lib/facet-counts";
import { MATERIAL_TAXONOMY } from "@/lib/material-taxonomy";
import { cn } from "@/lib/utils";
export interface DiscoveryFilterValues {
  sourceFilter: SourceFilter;
  assetCategory: AssetCategoryFilter;
  stateFilter: string;
  regionFilter: string;
  cityFilter: string;
  materialFilter: string;
  lotType: LotTypeFilter;
  confidence: ConfidenceFilter;
  priceStatus: PriceStatusFilter;
  emdStatus: EmdStatusFilter;
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
  pinCode: string;
  radiusKm: number;
  emdEligibleOnly: boolean;
  gstFilter: string;
  materialTreeIds: Set<string>;
}
export interface DiscoveryFilterSetters {
  setSourceFilter: (v: SourceFilter) => void;
  setAssetCategory: (v: AssetCategoryFilter) => void;
  setStateFilter: (v: string) => void;
  setRegionFilter: (v: string) => void;
  setCityFilter: (v: string) => void;
  setMaterialFilter: (v: string) => void;
  setLotType: (v: LotTypeFilter) => void;
  setConfidence: (v: ConfidenceFilter) => void;
  setPriceStatus: (v: PriceStatusFilter) => void;
  setEmdStatus: (v: EmdStatusFilter) => void;
  setDatePreset: (v: DatePreset) => void;
  setCustomFrom: (v: string) => void;
  setCustomTo: (v: string) => void;
  setListedPreset: (v: ListedPreset) => void;
  setListedFrom: (v: string) => void;
  setListedTo: (v: string) => void;
  setImportedPreset: (v: ImportedPreset) => void;
  setImportedFrom: (v: string) => void;
  setImportedTo: (v: string) => void;
  setQuantityMin: (v: QuantityMinFilter) => void;
  setLargeLotsOnly: (v: boolean) => void;
  setDocumentsFilter: (v: DocumentsFilter) => void;
  setIncludeClosed: (v: boolean) => void;
  setWatchlistOnly: (v: boolean) => void;
  setPinCode: (v: string) => void;
  setRadiusKm: (v: number) => void;
  setEmdEligibleOnly: (v: boolean) => void;
  setGstFilter: (v: string) => void;
  setMaterialTreeIds: (v: Set<string>) => void;
}
function PillButton({
  active,
  onClick,
  count,
  children,
}: {
  active: boolean;
  onClick: () => void;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "min-h-[44px] rounded-full border px-4 py-2 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-ring",
        active
          ? "border-action bg-muted text-action"
          : "border-border bg-card text-muted-foreground hover:bg-muted",
      )}
    >
      {" "}
      {children}{" "}
      {count != null && count > 0 && (
        <span className="ml-1 tabular-nums text-muted-foreground">
          ({count})
        </span>
      )}{" "}
    </button>
  );
}
function FilterSection({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 border-b border-border pb-5 last:border-b-0 last:pb-0">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <h3 className="text-title text-foreground">{title}</h3>
      </div>
      {children}
    </section>
  );
}
function facetCount(
  facetCounts: FacetCounts | undefined,
  facet: keyof FacetCounts,
  key: string,
): number | undefined {
  if (!facetCounts) return undefined;
  const count = facetCounts[facet][key];
  return count && count > 0 ? count : undefined;
}
function FilterSections({
  filters,
  setters,
  facetCounts,
  regionOptions,
  stateOptions,
  cityOptions,
}: {
  filters: DiscoveryFilterValues;
  setters: DiscoveryFilterSetters;
  facetCounts?: FacetCounts;
  regionOptions: string[];
  stateOptions: string[];
  cityOptions: string[];
}) {
  const { gateFeature } = useUpgradePrompt();
  const showCustomRange =
    filters.datePreset === "custom" ||
    Boolean(filters.customFrom || filters.customTo);
  const showListedCustom =
    filters.listedPreset === "custom" ||
    Boolean(filters.listedFrom || filters.listedTo);
  const showImportedCustom =
    filters.importedPreset === "custom" ||
    Boolean(filters.importedFrom || filters.importedTo);
  return (
    <div className="space-y-5">
      {" "}
      <FilterSection icon={Calendar} title="Time">
        {" "}
        <div className="flex flex-wrap gap-2">
          {" "}
          {DATE_PRESETS.map((p) => (
            <PillButton
              key={p.id}
              active={filters.datePreset === p.id}
              count={facetCount(facetCounts, "datePreset", p.id)}
              onClick={() => {
                setters.setDatePreset(p.id);
                setters.setCustomFrom("");
                setters.setCustomTo("");
              }}
            >
              {" "}
              {p.label}{" "}
            </PillButton>
          ))}{" "}
          <PillButton
            active={filters.datePreset === "custom"}
            onClick={() => setters.setDatePreset("custom")}
          >
            {" "}
            {DATE_PRESET_LABELS.custom}{" "}
          </PillButton>{" "}
        </div>{" "}
        {showCustomRange && (
          <div className="flex flex-wrap items-center gap-2">
            {" "}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {" "}
              From{" "}
              <Input
                type="date"
                value={filters.customFrom}
                onChange={(e) => {
                  setters.setCustomFrom(e.target.value);
                  if (filters.datePreset !== "custom")
                    setters.setDatePreset("custom");
                }}
                className="h-8 w-auto"
              />{" "}
            </label>{" "}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {" "}
              To{" "}
              <Input
                type="date"
                value={filters.customTo}
                onChange={(e) => {
                  setters.setCustomTo(e.target.value);
                  if (filters.datePreset !== "custom")
                    setters.setDatePreset("custom");
                }}
                className="h-8 w-auto"
              />{" "}
            </label>{" "}
          </div>
        )}{" "}
        <div className="flex flex-wrap gap-2 pt-1">
          {" "}
          <span className="w-full text-[11px] font-medium text-muted-foreground">
            Listed date
          </span>{" "}
          {LISTED_PRESETS.map((p) => (
            <PillButton
              key={p.id}
              active={filters.listedPreset === p.id}
              onClick={() => {
                setters.setListedPreset(p.id);
                setters.setListedFrom("");
                setters.setListedTo("");
              }}
            >
              {" "}
              {p.label}{" "}
            </PillButton>
          ))}{" "}
          <PillButton
            active={filters.listedPreset === "custom"}
            onClick={() => setters.setListedPreset("custom")}
          >
            {" "}
            {LISTED_PRESET_LABELS.custom}{" "}
          </PillButton>{" "}
        </div>{" "}
        {showListedCustom && (
          <div className="flex flex-wrap items-center gap-2">
            {" "}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {" "}
              From{" "}
              <Input
                type="date"
                value={filters.listedFrom}
                onChange={(e) => {
                  setters.setListedFrom(e.target.value);
                  if (filters.listedPreset !== "custom")
                    setters.setListedPreset("custom");
                }}
                className="h-8 w-auto"
              />{" "}
            </label>{" "}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {" "}
              To{" "}
              <Input
                type="date"
                value={filters.listedTo}
                onChange={(e) => {
                  setters.setListedTo(e.target.value);
                  if (filters.listedPreset !== "custom")
                    setters.setListedPreset("custom");
                }}
                className="h-8 w-auto"
              />{" "}
            </label>{" "}
          </div>
        )}{" "}
        <div className="flex flex-wrap gap-2 pt-1">
          {" "}
          <span className="w-full text-[11px] font-medium text-muted-foreground">
            Imported date
          </span>{" "}
          {IMPORTED_PRESETS.map((p) => (
            <PillButton
              key={p.id}
              active={filters.importedPreset === p.id}
              onClick={() => {
                setters.setImportedPreset(p.id);
                setters.setImportedFrom("");
                setters.setImportedTo("");
              }}
            >
              {" "}
              {p.label}{" "}
            </PillButton>
          ))}{" "}
          <PillButton
            active={filters.importedPreset === "custom"}
            onClick={() => setters.setImportedPreset("custom")}
          >
            {" "}
            {IMPORTED_PRESET_LABELS.custom}{" "}
          </PillButton>{" "}
        </div>{" "}
        {showImportedCustom && (
          <div className="flex flex-wrap items-center gap-2">
            {" "}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {" "}
              From{" "}
              <Input
                type="date"
                value={filters.importedFrom}
                onChange={(e) => {
                  setters.setImportedFrom(e.target.value);
                  if (filters.importedPreset !== "custom")
                    setters.setImportedPreset("custom");
                }}
                className="h-8 w-auto"
              />{" "}
            </label>{" "}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {" "}
              To{" "}
              <Input
                type="date"
                value={filters.importedTo}
                onChange={(e) => {
                  setters.setImportedTo(e.target.value);
                  if (filters.importedPreset !== "custom")
                    setters.setImportedPreset("custom");
                }}
                className="h-8 w-auto"
              />{" "}
            </label>{" "}
          </div>
        )}{" "}
        <label className="flex min-h-[44px] items-center gap-3 text-body-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={!filters.includeClosed}
            onChange={(e) => setters.setIncludeClosed(!e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          Active / upcoming only
        </label>
      </FilterSection>{" "}
      <FilterSection icon={MapPin} title="Location">
        {" "}
        <div className="flex flex-wrap gap-2">
          {" "}
          <Select
            value={filters.stateFilter}
            onChange={(e) => setters.setStateFilter(e.target.value)}
            className="h-9 min-w-[140px] text-sm"
            aria-label="State"
          >
            {" "}
            {stateOptions.map((s) => (
              <option key={s} value={s}>
                {" "}
                {s === "All" ? "All states" : s}{" "}
                {facetCount(facetCounts, "state", s) != null
                  ? ` (${facetCount(facetCounts, "state", s)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <Select
            value={filters.cityFilter}
            onChange={(e) => setters.setCityFilter(e.target.value)}
            className="h-9 min-w-[140px] text-sm"
            aria-label="City"
          >
            {" "}
            {cityOptions.map((c) => (
              <option key={c} value={c}>
                {" "}
                {c === "All" ? "All cities" : c}{" "}
                {facetCount(facetCounts, "city", c) != null
                  ? ` (${facetCount(facetCounts, "city", c)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <Select
            value={filters.regionFilter}
            onChange={(e) => setters.setRegionFilter(e.target.value)}
            className="h-9 min-w-[140px] text-sm"
            aria-label="Region"
          >
            {" "}
            {regionOptions.map((r) => (
              <option key={r} value={r}>
                {" "}
                {r === "All" ? "All regions" : r}{" "}
                {facetCount(facetCounts, "region", r) != null
                  ? ` (${facetCount(facetCounts, "region", r)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
        </div>{" "}
      </FilterSection>{" "}
      <FilterSection icon={Package} title="Material">
        {" "}
        <div className="flex flex-wrap gap-2">
          {" "}
          <Select
            value={filters.assetCategory}
            onChange={(e) =>
              setters.setAssetCategory(e.target.value as AssetCategoryFilter)
            }
            className="h-9 min-w-[150px] text-sm"
            aria-label="Asset category"
          >
            {" "}
            {ASSET_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {" "}
                {categoryLabel(c)}{" "}
                {facetCount(facetCounts, "assetCategory", c) != null
                  ? ` (${facetCount(facetCounts, "assetCategory", c)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <Select
            value={filters.materialFilter}
            onChange={(e) => setters.setMaterialFilter(e.target.value)}
            className="h-9 min-w-[160px] text-sm"
            aria-label="Material category"
          >
            {" "}
            {DISPLAY_MATERIAL_CATEGORIES.map((m) => (
              <option key={m.id} value={m.id}>
                {" "}
                {m.label}{" "}
                {facetCount(facetCounts, "material", m.id) != null
                  ? ` (${facetCount(facetCounts, "material", m.id)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <Select
            value={filters.quantityMin}
            onChange={(e) =>
              setters.setQuantityMin(e.target.value as QuantityMinFilter)
            }
            className="h-9 min-w-[130px] text-sm"
            aria-label="Minimum quantity"
          >
            {" "}
            {QUANTITY_MIN_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {" "}
                {o.label}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <PillButton
            active={filters.largeLotsOnly}
            onClick={() => {
              const next = !filters.largeLotsOnly;
              if (
                next &&
                !gateFeature(
                  "filter_large_lots",
                  canUsePremiumFeature("filter_large_lots"),
                  "filter_drawer",
                )
              ) {
                return;
              }
              setters.setLargeLotsOnly(next);
            }}
          >
            {" "}
            Large lots (100+ MT){" "}
          </PillButton>{" "}
          <Select
            value={filters.lotType}
            onChange={(e) =>
              setters.setLotType(e.target.value as LotTypeFilter)
            }
            className="h-9 min-w-[120px] text-sm"
            aria-label="Lot type"
          >
            {" "}
            {LOT_TYPES.map((t) => (
              <option key={t} value={t}>
                {" "}
                {t === "All" ? "All lot types" : t}{" "}
                {facetCount(facetCounts, "lotType", t) != null
                  ? ` (${facetCount(facetCounts, "lotType", t)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
        </div>{" "}
      </FilterSection>{" "}
      <FilterSection icon={Store} title="Commercial">
        {" "}
        <div className="flex flex-wrap gap-2">
          {" "}
          <Select
            value={filters.priceStatus}
            onChange={(e) =>
              setters.setPriceStatus(e.target.value as PriceStatusFilter)
            }
            className="h-9 min-w-[150px] text-sm"
            aria-label="Price status"
          >
            {" "}
            {PRICE_STATUS.map((p) => (
              <option key={p} value={p}>
                {" "}
                {p === "All" ? "All price types" : p.replace(/_/g, " ")}{" "}
                {facetCount(facetCounts, "priceStatus", p) != null
                  ? ` (${facetCount(facetCounts, "priceStatus", p)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <Select
            value={filters.emdStatus}
            onChange={(e) =>
              setters.setEmdStatus(e.target.value as EmdStatusFilter)
            }
            className="h-9 min-w-[150px] text-sm"
            aria-label="EMD status"
          >
            {" "}
            {EMD_STATUS.map((e) => (
              <option key={e} value={e}>
                {" "}
                {e === "All" ? "All EMD types" : e.replace(/_/g, " ")}{" "}
                {facetCount(facetCounts, "emdStatus", e) != null
                  ? ` (${facetCount(facetCounts, "emdStatus", e)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
        </div>{" "}
      </FilterSection>{" "}
      <FilterSection icon={Shield} title="Quality">
        {" "}
        <div className="flex flex-wrap gap-2">
          {" "}
          <Select
            value={filters.confidence}
            onChange={(e) =>
              setters.setConfidence(e.target.value as ConfidenceFilter)
            }
            className="h-9 min-w-[140px] text-sm"
            aria-label="Parse confidence"
          >
            {" "}
            {CONFIDENCE.map((c) => (
              <option key={c} value={c}>
                {" "}
                {c === "All" ? "All confidence" : c}{" "}
                {facetCount(facetCounts, "confidence", c) != null
                  ? ` (${facetCount(facetCounts, "confidence", c)})`
                  : ""}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
          <Select
            value={filters.documentsFilter}
            onChange={(e) =>
              setters.setDocumentsFilter(e.target.value as DocumentsFilter)
            }
            className="h-9 min-w-[140px] text-sm"
            aria-label="Documents filter"
          >
            {" "}
            {DOCUMENTS_FILTER_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {" "}
                {o.label}{" "}
              </option>
            ))}{" "}
          </Select>{" "}
        </div>{" "}
      </FilterSection>{" "}
      <FilterSection icon={Sparkles} title="Source">
        {" "}
        <div className="flex flex-wrap gap-2">
          {" "}
          {SOURCES.map((s) => (
            <PillButton
              key={s}
              active={filters.sourceFilter === s}
              count={
                s === "All" ? undefined : facetCount(facetCounts, "source", s)
              }
              onClick={() => setters.setSourceFilter(s)}
            >
              {" "}
              {s === "All" ? "All sources" : sourceLabel(s)}{" "}
            </PillButton>
          ))}{" "}
        </div>{" "}
        <label className="flex min-h-[44px] items-center gap-3 text-body-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={filters.watchlistOnly}
            onChange={(e) => setters.setWatchlistOnly(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          Watchlist only
        </label>
      </FilterSection>{" "}
      <FilterSection icon={MapPin} title="Logistics & EMD">
        {" "}
        <div className="space-y-2">
          {" "}
          <Input
            placeholder="Yard PIN code"
            value={filters.pinCode}
            onChange={(e) => setters.setPinCode(e.target.value)}
            className="h-9"
          />{" "}
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            {" "}
            Radius (km){" "}
            <Input
              type="number"
              min={0}
              max={1000}
              value={filters.radiusKm || ""}
              onChange={(e) => {
                const v = Number(e.target.value) || 0;
                if (
                  v > 0 &&
                  !gateFeature(
                    "filter_geo_radius",
                    canUsePremiumFeature("filter_geo_radius"),
                    "filter_drawer",
                  )
                ) {
                  return;
                }
                setters.setRadiusKm(v);
              }}
              className="h-8 w-24"
            />{" "}
          </label>{" "}
          <label className="flex min-h-[44px] items-center gap-3 text-body-sm">
            <input
              type="checkbox"
              checked={filters.emdEligibleOnly}
              onChange={(e) => {
                const next = e.target.checked;
                if (
                  next &&
                  !gateFeature(
                    "filter_emd_eligible",
                    canUsePremiumFeature("filter_emd_eligible"),
                    "filter_drawer",
                  )
                ) {
                  return;
                }
                setters.setEmdEligibleOnly(next);
              }}
              className="h-4 w-4 rounded border-border"
            />
            EMD balance allows bidding
          </label>
          <Select
            value={filters.gstFilter}
            onChange={(e) => {
              const v = e.target.value;
              if (
                v !== "all" &&
                !gateFeature(
                  "filter_gst_slab",
                  canUsePremiumFeature("filter_gst_slab"),
                  "filter_drawer",
                )
              ) {
                return;
              }
              setters.setGstFilter(v);
            }}
            className="h-9 text-sm"
            aria-label="GST slab"
          >
            {" "}
            <option value="all">All GST slabs</option>{" "}
            <option value="18">18% GST</option>{" "}
            <option value="5">5% GST</option>{" "}
          </Select>{" "}
        </div>{" "}
      </FilterSection>{" "}
      <FilterSection icon={Package} title="Material tree">
        {" "}
        <div className="space-y-1 text-sm">
          {" "}
          {MATERIAL_TAXONOMY.map((node) => (
            <label key={node.id} className="flex min-h-[44px] items-center gap-3 text-body-sm">
              <input
                type="checkbox"
                checked={filters.materialTreeIds.has(node.id)}
                onChange={(e) => {
                  const next = new Set(filters.materialTreeIds);
                  if (e.target.checked) {
                    if (
                      !gateFeature(
                        "filter_material_tree",
                        canUsePremiumFeature("filter_material_tree"),
                        "filter_drawer",
                      )
                    ) {
                      return;
                    }
                    next.add(node.id);
                  } else next.delete(node.id);
                  setters.setMaterialTreeIds(next);
                }}
                className="h-4 w-4 rounded border-border"
              />
              {node.label}
            </label>
          ))}{" "}
        </div>{" "}
      </FilterSection>{" "}
    </div>
  );
}
export function FilterDrawer({
  open,
  filters,
  setters,
  facetCounts,
  regionOptions,
  stateOptions,
  cityOptions,
  onClose,
  onReset,
  className,
}: {
  open: boolean;
  filters: DiscoveryFilterValues;
  setters: DiscoveryFilterSetters;
  facetCounts?: FacetCounts;
  regionOptions: string[];
  stateOptions: string[];
  cityOptions: string[];
  onClose: () => void;
  onReset: () => void;
  className?: string;
}) {
  const sections = (
    <FilterSections
      filters={filters}
      setters={setters}
      facetCounts={facetCounts}
      regionOptions={regionOptions}
      stateOptions={stateOptions}
      cityOptions={cityOptions}
    />
  );
  return (
    <>
      {" "}
      <FilterBottomSheet
        open={open}
        onClose={onClose}
        onApply={onClose}
        onReset={onReset}
      >
        {" "}
        {sections}{" "}
      </FilterBottomSheet>{" "}
      {open && (
        <aside
          className={cn(
            "surface-elevated hidden max-h-[calc(100vh-8rem)] overflow-y-auto p-4 sm:block",
            className,
          )}
        >
          {" "}
          <div className="mb-3 flex items-center justify-between">
            {" "}
            <h2 className="text-title text-foreground">Filters</h2>
            <button
              type="button"
              onClick={onReset}
              className="text-xs font-medium link-action"
            >
              {" "}
              Reset all{" "}
            </button>{" "}
          </div>{" "}
          {sections}{" "}
        </aside>
      )}{" "}
    </>
  );
}
