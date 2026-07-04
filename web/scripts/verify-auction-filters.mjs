#!/usr/bin/env node
/**
 * IST date-filter self-tests (mirrors web/src/lib/auction-filters.ts logic).
 */
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;
const IST = "Asia/Kolkata";

function ymdFormatter() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function istTodayYmd() {
  return ymdFormatter().format(new Date());
}

function addDaysYmd(ymd, days) {
  const [y, m, d] = ymd.split("-").map(Number);
  const dayNum = Math.floor(Date.UTC(y, m - 1, d) / DAY_MS) + days;
  return new Date(dayNum * DAY_MS).toISOString().slice(0, 10);
}

function istYmdStartMs(ymd) {
  const [y, m, d] = ymd.split("-").map(Number);
  return Date.UTC(y, m - 1, d) - IST_OFFSET_MS;
}

function istYmdEndMs(ymd) {
  return istYmdStartMs(ymd) + DAY_MS - 1;
}

function parseClosingMs(closing) {
  if (!closing) return null;
  const t = Date.parse(closing);
  return Number.isNaN(t) ? null : t;
}

function isDateFilterActive(preset, customFrom, customTo) {
  if (preset !== "all") return true;
  return Boolean(customFrom || customTo);
}

function resolveDateRange(preset, customFrom, customTo) {
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

function matchesClosingDateFilter(closing, preset, customFrom, customTo) {
  const effectivePreset =
    preset === "all" && (customFrom || customTo) ? "custom" : preset;
  if (!isDateFilterActive(effectivePreset, customFrom, customTo)) return true;
  const closingMs = parseClosingMs(closing);
  if (closingMs === null) return false;
  const range = resolveDateRange(effectivePreset, customFrom, customTo);
  if (!range) return true;
  return closingMs >= range.start && closingMs <= range.end;
}

function parseListedMs(auction) {
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

function isListedFilterActive(preset, customFrom, customTo) {
  if (preset !== "all") return true;
  return Boolean(customFrom || customTo);
}

function resolveListedRange(preset, customFrom, customTo) {
  const today = istTodayYmd();
  switch (preset) {
    case "today":
      return { start: istYmdStartMs(today), end: istYmdEndMs(today) };
    case "yesterday": {
      const y = addDaysYmd(today, -1);
      return { start: istYmdStartMs(y), end: istYmdEndMs(y) };
    }
    case "last3":
      return { start: istYmdStartMs(addDaysYmd(today, -2)), end: istYmdEndMs(today) };
    case "last7":
      return { start: istYmdStartMs(addDaysYmd(today, -6)), end: istYmdEndMs(today) };
    case "last14":
      return { start: istYmdStartMs(addDaysYmd(today, -13)), end: istYmdEndMs(today) };
    case "custom":
      if (!customFrom && !customTo) return null;
      return {
        start: customFrom ? istYmdStartMs(customFrom) : Number.NEGATIVE_INFINITY,
        end: customTo ? istYmdEndMs(customTo) : Number.POSITIVE_INFINITY,
      };
    default:
      return null;
  }
}

function matchesListedDateFilter(auction, preset, customFrom, customTo) {
  const effective =
    preset === "all" && (customFrom || customTo) ? "custom" : preset;
  if (!isListedFilterActive(effective, customFrom, customTo)) return true;
  const listedMs = parseListedMs(auction);
  if (listedMs === null) return false;
  const range = resolveListedRange(effective, customFrom, customTo);
  if (!range) return true;
  return listedMs >= range.start && listedMs <= range.end;
}

function parseImportedMs(auction) {
  const iso = auction.imported_at ?? auction.first_seen_at;
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

function isImportedFilterActive(preset, customFrom, customTo) {
  if (preset !== "all") return true;
  return Boolean(customFrom || customTo);
}

function resolveImportedRange(preset, customFrom, customTo) {
  const today = istTodayYmd();
  switch (preset) {
    case "today":
      return { start: istYmdStartMs(today), end: istYmdEndMs(today) };
    case "yesterday": {
      const y = addDaysYmd(today, -1);
      return { start: istYmdStartMs(y), end: istYmdEndMs(y) };
    }
    case "last3":
      return { start: istYmdStartMs(addDaysYmd(today, -2)), end: istYmdEndMs(today) };
    case "last7":
      return { start: istYmdStartMs(addDaysYmd(today, -6)), end: istYmdEndMs(today) };
    case "custom":
      if (!customFrom && !customTo) return null;
      return {
        start: customFrom ? istYmdStartMs(customFrom) : Number.NEGATIVE_INFINITY,
        end: customTo ? istYmdEndMs(customTo) : Number.POSITIVE_INFINITY,
      };
    default:
      return null;
  }
}

function matchesImportedDateFilter(auction, preset, customFrom, customTo) {
  const effective =
    preset === "all" && (customFrom || customTo) ? "custom" : preset;
  if (!isImportedFilterActive(effective, customFrom, customTo)) return true;
  const importedMs = parseImportedMs(auction);
  if (importedMs === null) return false;
  const range = resolveImportedRange(effective, customFrom, customTo);
  if (!range) return true;
  return importedMs >= range.start && importedMs <= range.end;
}

function runTests() {
  const errors = [];
  const assert = (name, condition) => {
    if (!condition) errors.push(name);
  };

  const today = istTodayYmd();
  const sample = `${today}T07:00:00+05:30`;
  assert("today preset", matchesClosingDateFilter(sample, "today", "", ""));
  const tomorrow = addDaysYmd(today, 1);
  assert(
    "tomorrow preset",
    matchesClosingDateFilter(`${tomorrow}T12:00:00+05:30`, "tomorrow", "", ""),
  );
  assert(
    "custom inclusive",
    matchesClosingDateFilter(sample, "custom", today, tomorrow),
  );
  assert(
    "missing excluded when filtered",
    !matchesClosingDateFilter(null, "today", "", ""),
  );

  // Listed date filter tests
  const listedToday = { listed_date: today, listed_at: `${today}T09:00:00+05:30` };
  const listedYesterday = {
    listed_date: addDaysYmd(today, -1),
    listed_at: `${addDaysYmd(today, -1)}T09:00:00+05:30`,
  };
  const listedOld = {
    listed_date: addDaysYmd(today, -30),
    listed_at: `${addDaysYmd(today, -30)}T09:00:00+05:30`,
  };
  const listedMissing = {};

  assert(
    "listed today preset matches listed today",
    matchesListedDateFilter(listedToday, "today", "", ""),
  );
  assert(
    "listed today excludes yesterday",
    !matchesListedDateFilter(listedYesterday, "today", "", ""),
  );
  assert(
    "listed yesterday preset matches yesterday",
    matchesListedDateFilter(listedYesterday, "yesterday", "", ""),
  );
  assert(
    "listed last7 includes today",
    matchesListedDateFilter(listedToday, "last7", "", ""),
  );
  assert(
    "listed last7 excludes 30-days-old",
    !matchesListedDateFilter(listedOld, "last7", "", ""),
  );
  assert(
    "listed last14 excludes 30-days-old",
    !matchesListedDateFilter(listedOld, "last14", "", ""),
  );
  assert(
    "listed missing excluded when filter active",
    !matchesListedDateFilter(listedMissing, "today", "", ""),
  );
  assert(
    "listed missing included when no filter",
    matchesListedDateFilter(listedMissing, "all", "", ""),
  );
  assert(
    "listed custom range inclusive",
    matchesListedDateFilter(
      listedYesterday,
      "custom",
      addDaysYmd(today, -2),
      today,
    ),
  );
  assert(
    "listed custom excludes outside range",
    !matchesListedDateFilter(listedOld, "custom", addDaysYmd(today, -7), today),
  );

  const importedToday = {
    imported_at: `${today}T09:00:00+05:30`,
    first_seen_at: `${today}T09:00:00+05:30`,
  };
  const importedYesterday = {
    imported_at: `${addDaysYmd(today, -1)}T09:00:00+05:30`,
  };
  const importedMissing = {};

  assert(
    "imported today preset",
    matchesImportedDateFilter(importedToday, "today", "", ""),
  );
  assert(
    "imported today excludes yesterday",
    !matchesImportedDateFilter(importedYesterday, "today", "", ""),
  );
  assert(
    "imported missing excluded when filter active",
    !matchesImportedDateFilter(importedMissing, "today", "", ""),
  );
  assert(
    "imported missing included when no filter",
    matchesImportedDateFilter(importedMissing, "all", "", ""),
  );

  return errors;
}

const errors = runTests();
if (errors.length) {
  console.error("FAIL auction-filters:", errors.join(", "));
  process.exit(1);
}
console.log("OK  auction-filters IST self-tests");
