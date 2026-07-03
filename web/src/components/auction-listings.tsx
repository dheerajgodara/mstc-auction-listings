"use client";

import { useEffect, useMemo, useState } from "react";
import { Calendar, Clock, Filter, Search, X } from "lucide-react";
import { AuctionCard } from "@/components/auction-card";
import { PaginationBar } from "@/components/pagination-bar";
import { Chip, Input, Select } from "@/components/ui/primitives";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  type DatePreset,
  isActiveOrUpcoming,
  isDateFilterActive,
  matchesClosingDateFilter,
  sortAuctions,
  type SortOption,
} from "@/lib/auction-filters";
import { formatDateTime } from "@/lib/utils";
import type { AssetCategory, AuctionRecord, AuctionSource, EmdParseStatus } from "@/types/auction";
import { cn } from "@/lib/utils";

const SOURCES = ["All", "mstc", "eauction", "gem_forward"] as const;
const ASSET_CATEGORIES = [
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

const SOURCE_LABELS: Record<AuctionSource, string> = {
  mstc: "MSTC",
  eauction: "eAuction",
  gem_forward: "GeM Forward",
};

function sourceLabel(source?: AuctionSource | null): string {
  if (!source || source === "mstc") return "MSTC";
  return SOURCE_LABELS[source] ?? source;
}

function categoryLabel(category: AssetCategory): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}

const LOT_TYPES = ["All", "General", "RVSF", "Hazardous"] as const;
const CONFIDENCE = ["All", "high", "medium", "low", "minimal"] as const;
const PRICE_STATUS = [
  "All",
  "numeric",
  "range",
  "percentage_based",
  "not_disclosed",
  "missing",
] as const;
const EMD_STATUS = [
  "All",
  "auction_wise",
  "item_wise",
  "not_required",
  "missing",
  "unknown",
] as const;

const DATE_PRESETS: { id: DatePreset; label: string }[] = [
  { id: "today", label: "Closing today" },
  { id: "tomorrow", label: "Closing tomorrow" },
  { id: "next3", label: "Next 3 days" },
  { id: "next7", label: "Next 7 days" },
];

const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  all: "All dates",
  today: "Closing today",
  tomorrow: "Closing tomorrow",
  next3: "Next 3 days",
  next7: "Next 7 days",
  custom: "Custom range",
};

function matchesQuery(auction: AuctionRecord, q: string): boolean {
  if (!q.trim()) return true;
  const needle = q.toLowerCase();
  const hay = [
    auction.search_text,
    auction.seller,
    auction.location,
    auction.state,
    auction.region,
    auction.item_summary,
    ...auction.lots.map(
      (l) => `${l.item_title} ${l.item_description ?? ""} ${l.location ?? ""}`,
    ),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(needle);
}

function PillButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50",
        active ? "btn-pill-active" : "btn-pill-inactive",
      )}
    >
      {children}
    </button>
  );
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
      className="inline-flex items-center gap-1 rounded-full border border-cyan-200/80 bg-cyan-50/90 px-2.5 py-1 text-xs font-medium text-cyan-900 hover:bg-cyan-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
    >
      {label}
      <X className="h-3 w-3" />
    </button>
  );
}

export function AuctionListings({
  auctions,
  generatedAt,
  total,
}: {
  auctions: AuctionRecord[];
  generatedAt?: string;
  total?: number;
}) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 200);
  const [sourceFilter, setSourceFilter] = useState<(typeof SOURCES)[number]>("All");
  const [assetCategory, setAssetCategory] =
    useState<(typeof ASSET_CATEGORIES)[number]>("All");
  const [stateFilter, setStateFilter] = useState("All");
  const [regionFilter, setRegionFilter] = useState("All");
  const [lotType, setLotType] = useState<(typeof LOT_TYPES)[number]>("All");
  const [confidence, setConfidence] =
    useState<(typeof CONFIDENCE)[number]>("All");
  const [priceStatus, setPriceStatus] =
    useState<(typeof PRICE_STATUS)[number]>("All");
  const [emdStatus, setEmdStatus] = useState<(typeof EMD_STATUS)[number]>("All");
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [sortBy, setSortBy] = useState<SortOption>("closing_asc");
  const [includeClosed, setIncludeClosed] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const totalCount = total ?? auctions.length;

  const regions = useMemo(() => {
    const r = new Set(auctions.map((a) => a.region).filter(Boolean));
    return ["All", ...Array.from(r).sort()];
  }, [auctions]);

  const states = useMemo(() => {
    const s = new Set(auctions.map((a) => a.state).filter(Boolean) as string[]);
    return ["All", ...Array.from(s).sort()];
  }, [auctions]);

  const effectiveDatePreset =
    datePreset === "all" && (customFrom || customTo) ? "custom" : datePreset;

  const filtered = useMemo(() => {
    return auctions.filter((a) => {
      if (!matchesQuery(a, debouncedQuery)) return false;
      if (!includeClosed && !isActiveOrUpcoming(a.closing)) return false;
      const auctionSource = a.source ?? "mstc";
      if (sourceFilter !== "All" && auctionSource !== sourceFilter) return false;
      if (assetCategory !== "All" && a.asset_category !== assetCategory) return false;
      if (stateFilter !== "All" && a.state !== stateFilter) return false;
      if (regionFilter !== "All" && a.region !== regionFilter) return false;
      if (lotType !== "All" && !a.lot_types?.includes(lotType)) return false;
      if (confidence !== "All" && a.parse_confidence !== confidence) return false;
      if (priceStatus !== "All" && a.price_parse_status !== priceStatus) {
        return false;
      }
      if (
        emdStatus !== "All" &&
        a.emd_parse_status !== (emdStatus as EmdParseStatus)
      ) {
        return false;
      }
      if (
        !matchesClosingDateFilter(
          a.closing,
          effectiveDatePreset,
          customFrom,
          customTo,
        )
      ) {
        return false;
      }
      return true;
    });
  }, [
    auctions,
    debouncedQuery,
    includeClosed,
    sourceFilter,
    assetCategory,
    stateFilter,
    regionFilter,
    lotType,
    confidence,
    priceStatus,
    emdStatus,
    effectiveDatePreset,
    customFrom,
    customTo,
  ]);

  const sorted = useMemo(
    () => sortAuctions(filtered, sortBy),
    [filtered, sortBy],
  );

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, totalPages);

  const paginated = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return sorted.slice(start, start + pageSize);
  }, [sorted, safePage, pageSize]);

  useEffect(() => {
    setPage(1);
  }, [
    debouncedQuery,
    sourceFilter,
    assetCategory,
    stateFilter,
    regionFilter,
    lotType,
    confidence,
    priceStatus,
    emdStatus,
    datePreset,
    customFrom,
    customTo,
    sortBy,
    includeClosed,
    pageSize,
  ]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const clearAllFilters = () => {
    setQuery("");
    setSourceFilter("All");
    setAssetCategory("All");
    setStateFilter("All");
    setRegionFilter("All");
    setLotType("All");
    setConfidence("All");
    setPriceStatus("All");
    setEmdStatus("All");
    setDatePreset("all");
    setCustomFrom("");
    setCustomTo("");
    setIncludeClosed(true);
  };

  const activeChips = useMemo(() => {
    const chips: { key: string; label: string; onRemove: () => void }[] = [];

    if (query.trim()) {
      chips.push({
        key: "search",
        label: `Search: ${query.trim()}`,
        onRemove: () => setQuery(""),
      });
    }
    if (isDateFilterActive(effectiveDatePreset, customFrom, customTo)) {
      const dateLabel =
        effectiveDatePreset === "custom"
          ? `Dates: ${customFrom || "…"} – ${customTo || "…"}`
          : DATE_PRESET_LABELS[effectiveDatePreset];
      chips.push({
        key: "date",
        label: dateLabel,
        onRemove: () => {
          setDatePreset("all");
          setCustomFrom("");
          setCustomTo("");
        },
      });
    }
    if (sourceFilter !== "All") {
      chips.push({
        key: "source",
        label: `Source: ${sourceLabel(sourceFilter)}`,
        onRemove: () => setSourceFilter("All"),
      });
    }
    if (assetCategory !== "All") {
      chips.push({
        key: "category",
        label: `Category: ${categoryLabel(assetCategory)}`,
        onRemove: () => setAssetCategory("All"),
      });
    }
    if (stateFilter !== "All") {
      chips.push({
        key: "state",
        label: `State: ${stateFilter}`,
        onRemove: () => setStateFilter("All"),
      });
    }
    if (regionFilter !== "All") {
      chips.push({
        key: "region",
        label: `Region: ${regionFilter}`,
        onRemove: () => setRegionFilter("All"),
      });
    }
    if (confidence !== "All") {
      chips.push({
        key: "confidence",
        label: `Confidence: ${confidence}`,
        onRemove: () => setConfidence("All"),
      });
    }
    if (priceStatus !== "All") {
      chips.push({
        key: "price",
        label: `Price: ${priceStatus.replace(/_/g, " ")}`,
        onRemove: () => setPriceStatus("All"),
      });
    }
    if (emdStatus !== "All") {
      chips.push({
        key: "emd",
        label: `EMD: ${emdStatus.replace(/_/g, " ")}`,
        onRemove: () => setEmdStatus("All"),
      });
    }
    if (lotType !== "All") {
      chips.push({
        key: "lotType",
        label: `Type: ${lotType}`,
        onRemove: () => setLotType("All"),
      });
    }
    if (!includeClosed) {
      chips.push({
        key: "closed",
        label: "Active/upcoming only",
        onRemove: () => setIncludeClosed(true),
      });
    }

    return chips;
  }, [
    query,
    effectiveDatePreset,
    customFrom,
    customTo,
    sourceFilter,
    assetCategory,
    stateFilter,
    regionFilter,
    confidence,
    priceStatus,
    emdStatus,
    lotType,
    includeClosed,
  ]);

  const showCustomRange =
    datePreset === "custom" || Boolean(customFrom || customTo);

  return (
    <div className="space-y-4">
      <header className="mx-auto max-w-6xl space-y-2 pt-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              Government Auction Listings
            </h1>
            <p className="max-w-2xl text-sm text-slate-600">
              Government auction opportunities from MSTC and other sources
            </p>
          </div>
          {generatedAt && (
            <Chip className="border-violet-200/80 bg-violet-50/90 text-violet-900 normal-case tracking-normal">
              <Clock className="mr-1 inline h-3 w-3" />
              Updated: {formatDateTime(generatedAt)}
            </Chip>
          )}
        </div>
      </header>

      <div className="sticky top-0 z-20 mx-auto max-w-6xl space-y-2">
        <div className="glass-panel p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[200px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cyan-600/70" />
              <Input
                className="h-9 pl-9"
                placeholder="Search item, seller, location…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <Select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="h-9 w-auto min-w-[140px] text-sm"
              aria-label="Sort auctions"
            >
              <option value="closing_asc">Closing soonest</option>
              <option value="opening_asc">Opening soonest</option>
              <option value="price_asc">Price low → high</option>
              <option value="price_desc">Price high → low</option>
            </Select>
            <button
              type="button"
              onClick={() => setFiltersOpen((v) => !v)}
              className={cn(
                "btn-glass inline-flex h-9 items-center gap-1.5 px-3 text-sm",
                filtersOpen && "btn-pill-active",
              )}
            >
              <Filter className="h-4 w-4" />
              Filters
            </button>
            <Chip className="hidden border-cyan-200/80 bg-cyan-50/90 text-cyan-900 normal-case tracking-normal sm:inline-flex">
              {filtered.length} of {totalCount}
            </Chip>
          </div>

          {activeChips.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-white/50 pt-2">
              {activeChips.map((chip) => (
                <RemovableChip
                  key={chip.key}
                  label={chip.label}
                  onRemove={chip.onRemove}
                />
              ))}
              <button
                type="button"
                onClick={clearAllFilters}
                className="text-xs font-medium text-cyan-800 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
              >
                Clear all
              </button>
            </div>
          )}

          {filtersOpen && (
            <div
              className={cn(
                "space-y-3 border-t border-white/50 pt-3",
                activeChips.length === 0 && "mt-2",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Calendar className="h-4 w-4 shrink-0 text-cyan-600/80" />
                {DATE_PRESETS.map((p) => (
                  <PillButton
                    key={p.id}
                    active={datePreset === p.id}
                    onClick={() => {
                      setDatePreset(p.id);
                      setCustomFrom("");
                      setCustomTo("");
                    }}
                  >
                    {p.label}
                  </PillButton>
                ))}
                <PillButton
                  active={datePreset === "custom"}
                  onClick={() => setDatePreset("custom")}
                >
                  Custom range
                </PillButton>
              </div>

              {showCustomRange && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    From
                    <Input
                      type="date"
                      value={customFrom}
                      onChange={(e) => {
                        setCustomFrom(e.target.value);
                        if (datePreset !== "custom") setDatePreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    To
                    <Input
                      type="date"
                      value={customTo}
                      onChange={(e) => {
                        setCustomTo(e.target.value);
                        if (datePreset !== "custom") setDatePreset("custom");
                      }}
                      className="h-8 w-auto"
                    />
                  </label>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={sourceFilter}
                  onChange={(e) =>
                    setSourceFilter(e.target.value as (typeof SOURCES)[number])
                  }
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {s === "All" ? "All sources" : sourceLabel(s)}
                    </option>
                  ))}
                </Select>
                <Select
                  value={assetCategory}
                  onChange={(e) =>
                    setAssetCategory(e.target.value as (typeof ASSET_CATEGORIES)[number])
                  }
                  className="h-9 w-auto min-w-[130px] text-sm"
                >
                  {ASSET_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c === "All" ? "All categories" : categoryLabel(c)}
                    </option>
                  ))}
                </Select>
                <Select
                  value={stateFilter}
                  onChange={(e) => setStateFilter(e.target.value)}
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {states.map((s) => (
                    <option key={s} value={s}>
                      {s === "All" ? "All states" : s}
                    </option>
                  ))}
                </Select>
                <Select
                  value={regionFilter}
                  onChange={(e) => setRegionFilter(e.target.value)}
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {regions.map((r) => (
                    <option key={r} value={r}>
                      {r === "All" ? "All regions" : r}
                    </option>
                  ))}
                </Select>
                <Select
                  value={lotType}
                  onChange={(e) =>
                    setLotType(e.target.value as (typeof LOT_TYPES)[number])
                  }
                  className="h-9 w-auto min-w-[110px] text-sm"
                >
                  {LOT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t === "All" ? "All types" : t}
                    </option>
                  ))}
                </Select>
                <Select
                  value={confidence}
                  onChange={(e) =>
                    setConfidence(e.target.value as (typeof CONFIDENCE)[number])
                  }
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {CONFIDENCE.map((c) => (
                    <option key={c} value={c}>
                      {c === "All" ? "All confidence" : c}
                    </option>
                  ))}
                </Select>
                <Select
                  value={priceStatus}
                  onChange={(e) =>
                    setPriceStatus(e.target.value as (typeof PRICE_STATUS)[number])
                  }
                  className="h-9 w-auto min-w-[130px] text-sm"
                >
                  {PRICE_STATUS.map((p) => (
                    <option key={p} value={p}>
                      {p === "All" ? "All prices" : p.replace(/_/g, " ")}
                    </option>
                  ))}
                </Select>
                <Select
                  value={emdStatus}
                  onChange={(e) =>
                    setEmdStatus(e.target.value as (typeof EMD_STATUS)[number])
                  }
                  className="h-9 w-auto min-w-[120px] text-sm"
                >
                  {EMD_STATUS.map((e) => (
                    <option key={e} value={e}>
                      {e === "All" ? "All EMD" : e.replace(/_/g, " ")}
                    </option>
                  ))}
                </Select>
              </div>

              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={includeClosed}
                  onChange={(e) => setIncludeClosed(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-400/50"
                />
                Include recently closed auctions
              </label>
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-4 pb-10">
        {sorted.length > 0 && (
          <PaginationBar
            page={safePage}
            pageSize={pageSize}
            totalItems={sorted.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}

        {sorted.length === 0 ? (
          <div className="glass-panel space-y-4 py-12 text-center">
            <p className="text-slate-600">No auctions match your filters.</p>
            <button type="button" onClick={clearAllFilters} className="btn-glass-primary">
              Clear all filters
            </button>
          </div>
        ) : (
          paginated.map((auction, i) => (
            <AuctionCard key={auction.id} auction={auction} index={i} />
          ))
        )}

        {sorted.length > 0 && (
          <PaginationBar
            page={safePage}
            pageSize={pageSize}
            totalItems={sorted.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>
    </div>
  );
}
