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

  return errors;
}

const errors = runTests();
if (errors.length) {
  console.error("FAIL auction-filters:", errors.join(", "));
  process.exit(1);
}
console.log("OK  auction-filters IST self-tests");
