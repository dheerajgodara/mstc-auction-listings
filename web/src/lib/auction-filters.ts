import type { AuctionRecord } from "@/types/auction";
import { auctionTotalMt } from "@/lib/display-enrichment";
import { sortByOpportunity } from "@/lib/opportunity-score";

const IST = "Asia/Kolkata";
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

export type DatePreset = "all" | "today" | "tomorrow" | "next3" | "next7" | "custom";

export type SortOption =
  | "closing_asc"
  | "opening_asc"
  | "price_asc"
  | "price_desc"
  | "best_opportunities"
  | "listed_desc"
  | "quantity_desc";

export type QuantityMinFilter = "any" | "10" | "50" | "100" | "500" | "1000";

export type ListedPreset =
  | "all"
  | "today"
  | "yesterday"
  | "last3"
  | "last7"
  | "last14"
  | "custom";

export interface ClosingUrgency {
  label: string;
  chipClass: string;
}

function ymdFormatter() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

/** Calendar date (YYYY-MM-DD) of an ISO timestamp in IST. */
export function closingIstYmd(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return ymdFormatter().format(new Date(t));
}

export function istTodayYmd(): string {
  return ymdFormatter().format(new Date());
}

export function addDaysYmd(ymd: string, days: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dayNum = Math.floor(Date.UTC(y, m - 1, d) / DAY_MS) + days;
  const dt = new Date(dayNum * DAY_MS);
  return dt.toISOString().slice(0, 10);
}

/** Start of IST calendar day as UTC epoch ms. */
export function istYmdStartMs(ymd: string): number {
  const [y, m, d] = ymd.split("-").map(Number);
  return Date.UTC(y, m - 1, d) - IST_OFFSET_MS;
}

/** End of IST calendar day as UTC epoch ms (inclusive). */
export function istYmdEndMs(ymd: string): number {
  return istYmdStartMs(ymd) + DAY_MS - 1;
}

export function parseClosingMs(
  closing: string | null | undefined,
): number | null {
  if (!closing) return null;
  const t = Date.parse(closing);
  return Number.isNaN(t) ? null : t;
}

export function parseAuctionMs(iso: string | null | undefined): number {
  if (!iso) return Number.MAX_SAFE_INTEGER;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? Number.MAX_SAFE_INTEGER : t;
}

function ymdDayNumber(ymd: string): number {
  const [y, m, d] = ymd.split("-").map(Number);
  return Math.floor(Date.UTC(y, m - 1, d) / DAY_MS);
}

export function ymdDiffDays(fromYmd: string, toYmd: string): number {
  return ymdDayNumber(toYmd) - ymdDayNumber(fromYmd);
}

export function isDateFilterActive(
  preset: DatePreset,
  customFrom: string,
  customTo: string,
): boolean {
  if (preset !== "all") return true;
  return Boolean(customFrom || customTo);
}

function resolveDateRange(
  preset: DatePreset,
  customFrom: string,
  customTo: string,
): { start: number; end: number } | null {
  const today = istTodayYmd();

  switch (preset) {
    case "today":
      return { start: istYmdStartMs(today), end: istYmdEndMs(today) };
    case "tomorrow": {
      const tomorrow = addDaysYmd(today, 1);
      return { start: istYmdStartMs(tomorrow), end: istYmdEndMs(tomorrow) };
    }
    case "next3":
      return {
        start: istYmdStartMs(today),
        end: istYmdEndMs(addDaysYmd(today, 2)),
      };
    case "next7":
      return {
        start: istYmdStartMs(today),
        end: istYmdEndMs(addDaysYmd(today, 6)),
      };
    case "custom": {
      if (!customFrom && !customTo) return null;
      return {
        start: customFrom ? istYmdStartMs(customFrom) : Number.NEGATIVE_INFINITY,
        end: customTo ? istYmdEndMs(customTo) : Number.POSITIVE_INFINITY,
      };
    }
    default:
      return null;
  }
}

export function matchesClosingDateFilter(
  closing: string | null | undefined,
  preset: DatePreset,
  customFrom: string,
  customTo: string,
): boolean {
  const effectivePreset =
    preset === "all" && (customFrom || customTo) ? "custom" : preset;

  if (!isDateFilterActive(effectivePreset, customFrom, customTo)) {
    return true;
  }

  const closingMs = parseClosingMs(closing);
  if (closingMs === null) return false;

  const range = resolveDateRange(effectivePreset, customFrom, customTo);
  if (!range) return true;

  return closingMs >= range.start && closingMs <= range.end;
}

/** Choose a datetime that represents "when this auction was listed". Prefer explicit listed_at. */
export function parseListedMs(auction: AuctionRecord): number | null {
  if (auction.listed_at) {
    const t = Date.parse(auction.listed_at);
    if (!Number.isNaN(t)) return t;
  }
  if (auction.listed_date) {
    const t = Date.parse(`${auction.listed_date}T00:00:00+05:30`);
    if (!Number.isNaN(t)) return t;
  }
  return null;
}

/** Resolve the IST calendar day for listed_at (falls back to listed_date). */
export function listedIstYmd(auction: AuctionRecord): string | null {
  if (auction.listed_date) return auction.listed_date;
  const ms = parseListedMs(auction);
  if (ms === null) return null;
  return ymdFormatter().format(new Date(ms));
}

export function isListedFilterActive(
  preset: ListedPreset,
  customFrom: string,
  customTo: string,
): boolean {
  if (preset !== "all") return true;
  return Boolean(customFrom || customTo);
}

function resolveListedRange(
  preset: ListedPreset,
  customFrom: string,
  customTo: string,
): { start: number; end: number } | null {
  const today = istTodayYmd();
  switch (preset) {
    case "today":
      return { start: istYmdStartMs(today), end: istYmdEndMs(today) };
    case "yesterday": {
      const y = addDaysYmd(today, -1);
      return { start: istYmdStartMs(y), end: istYmdEndMs(y) };
    }
    case "last3":
      return {
        start: istYmdStartMs(addDaysYmd(today, -2)),
        end: istYmdEndMs(today),
      };
    case "last7":
      return {
        start: istYmdStartMs(addDaysYmd(today, -6)),
        end: istYmdEndMs(today),
      };
    case "last14":
      return {
        start: istYmdStartMs(addDaysYmd(today, -13)),
        end: istYmdEndMs(today),
      };
    case "custom": {
      if (!customFrom && !customTo) return null;
      return {
        start: customFrom ? istYmdStartMs(customFrom) : Number.NEGATIVE_INFINITY,
        end: customTo ? istYmdEndMs(customTo) : Number.POSITIVE_INFINITY,
      };
    }
    default:
      return null;
  }
}

export function matchesListedDateFilter(
  auction: AuctionRecord,
  preset: ListedPreset,
  customFrom: string,
  customTo: string,
): boolean {
  const effective =
    preset === "all" && (customFrom || customTo) ? "custom" : preset;
  if (!isListedFilterActive(effective, customFrom, customTo)) return true;
  const listedMs = parseListedMs(auction);
  if (listedMs === null) return false;
  const range = resolveListedRange(effective, customFrom, customTo);
  if (!range) return true;
  return listedMs >= range.start && listedMs <= range.end;
}

export function matchesMaterialCategoryFilter(
  auction: AuctionRecord,
  materialCategory: string,
): boolean {
  if (materialCategory === "All") return true;
  return auction.display_material_category === materialCategory;
}

export function matchesCityFilter(auction: AuctionRecord, city: string): boolean {
  if (city === "All") return true;
  return (auction.display_location_city ?? "").toLowerCase() === city.toLowerCase();
}

export function matchesDisplayStateFilter(auction: AuctionRecord, state: string): boolean {
  if (state === "All") return true;
  const displayState = auction.display_location_state ?? auction.state;
  return (displayState ?? "").toLowerCase() === state.toLowerCase();
}

export function matchesQuantityMinFilter(
  auction: AuctionRecord,
  minMt: QuantityMinFilter,
): boolean {
  if (minMt === "any") return true;
  const total = auctionTotalMt(auction);
  if (total == null) return false;
  return total >= Number.parseFloat(minMt);
}

export function matchesLargeLotsOnly(auction: AuctionRecord, enabled: boolean): boolean {
  if (!enabled) return true;
  const total = auctionTotalMt(auction);
  return total != null && total >= 100;
}

export function isActiveOrUpcoming(
  closing: string | null | undefined,
): boolean {
  const closingMs = parseClosingMs(closing);
  if (closingMs === null) return true;
  return closingMs >= Date.now();
}

export function getClosingUrgency(
  closing: string | null | undefined,
): ClosingUrgency | null {
  const closingMs = parseClosingMs(closing);
  const closingYmd = closingIstYmd(closing);
  if (closingMs === null || !closingYmd) return null;

  const today = istTodayYmd();
  const now = Date.now();

  if (closingMs < now) {
    const daysSince = ymdDiffDays(closingYmd, today);
    if (daysSince <= 7) {
      return {
        label: "Closed recently",
        chipClass: "bg-slate-100 text-slate-700 border-slate-200/80",
      };
    }
    return {
      label: "Closed",
      chipClass: "bg-slate-100 text-slate-500 border-slate-200/80",
    };
  }

  const daysLeft = ymdDiffDays(today, closingYmd);
  if (daysLeft === 0) {
    return {
      label: "Closing today",
      chipClass: "bg-rose-50 text-rose-800 border-rose-200/80",
    };
  }
  if (daysLeft === 1) {
    return {
      label: "Closing tomorrow",
      chipClass: "bg-amber-50 text-amber-800 border-amber-200/80",
    };
  }
  return {
    label: `${daysLeft} days left`,
    chipClass: "bg-cyan-50 text-cyan-800 border-cyan-200/80",
  };
}

export function numericSortPrice(auction: AuctionRecord): number | null {
  const status = auction.price_parse_status;
  if (status !== "numeric" && status !== "range") return null;

  if (auction.min_start_price != null) return auction.min_start_price;

  const prices = auction.lots
    .map((l) => l.start_price_inr ?? l.start_price)
    .filter((p): p is number => p != null);
  return prices.length > 0 ? Math.min(...prices) : null;
}

export function sortAuctions(
  list: AuctionRecord[],
  sort: SortOption,
): AuctionRecord[] {
  return [...list].sort((a, b) => {
    switch (sort) {
      case "closing_asc":
        return parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
      case "opening_asc":
        return parseAuctionMs(a.opening) - parseAuctionMs(b.opening);
      case "price_asc": {
        const pa = numericSortPrice(a);
        const pb = numericSortPrice(b);
        if (pa == null && pb == null) {
          return parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
        }
        if (pa == null) return 1;
        if (pb == null) return -1;
        return pa - pb || parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
      }
      case "price_desc": {
        const pa = numericSortPrice(a);
        const pb = numericSortPrice(b);
        if (pa == null && pb == null) {
          return parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
        }
        if (pa == null) return 1;
        if (pb == null) return -1;
        return pb - pa || parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
      }
      case "best_opportunities":
        return 0;
      case "listed_desc": {
        const la = parseListedMs(a);
        const lb = parseListedMs(b);
        if (la === null && lb === null) {
          return parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
        }
        if (la === null) return 1;
        if (lb === null) return -1;
        return lb - la || parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
      }
      case "quantity_desc": {
        const qa = auctionTotalMt(a);
        const qb = auctionTotalMt(b);
        if (qa == null && qb == null) {
          return parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
        }
        if (qa == null) return 1;
        if (qb == null) return -1;
        return qb - qa || parseAuctionMs(a.closing) - parseAuctionMs(b.closing);
      }
      default:
        return 0;
    }
  });
}

export function applySortOption(
  list: AuctionRecord[],
  sort: SortOption,
): AuctionRecord[] {
  if (sort === "best_opportunities") {
    return sortByOpportunity(list);
  }
  return sortAuctions(list, sort);
}

/** Lightweight self-checks for IST date filtering (no test runner required). */
export function runAuctionFilterSelfTests(): string[] {
  const errors: string[] = [];

  const assert = (name: string, condition: boolean) => {
    if (!condition) errors.push(name);
  };

  const today = istTodayYmd();
  const start = istYmdStartMs(today);
  const end = istYmdEndMs(today);
  assert("start <= end", start <= end);

  const sample = `${today}T07:00:00+05:30`;
  const sampleMs = parseClosingMs(sample);
  assert(
    "sample closing within today IST bounds",
    sampleMs != null && sampleMs >= start && sampleMs <= end,
  );

  assert(
    "today preset matches sample",
    matchesClosingDateFilter(sample, "today", "", ""),
  );

  const tomorrow = addDaysYmd(today, 1);
  const tomorrowSample = `${tomorrow}T12:00:00+05:30`;
  assert(
    "tomorrow preset",
    matchesClosingDateFilter(tomorrowSample, "tomorrow", "", ""),
  );
  assert(
    "today preset excludes tomorrow",
    !matchesClosingDateFilter(tomorrowSample, "today", "", ""),
  );

  assert(
    "custom range inclusive",
    matchesClosingDateFilter(sample, "custom", today, tomorrow),
  );

  assert(
    "missing closing excluded when date filter active",
    !matchesClosingDateFilter(null, "today", "", ""),
  );

  assert(
    "missing closing included when no date filter",
    matchesClosingDateFilter(null, "all", "", ""),
  );

  return errors;
}
