import { LEGACY_EMD_BALANCE_KEY } from "@/lib/legacy-storage-keys";

const EMD_BALANCE_KEY = "emd-balance";

export function loadEmdBalance(): number {
  if (typeof window === "undefined") return 0;
  const v =
    localStorage.getItem(EMD_BALANCE_KEY) ??
    localStorage.getItem(LEGACY_EMD_BALANCE_KEY);
  const n = v ? Number(v) : 0;
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

export function saveEmdBalance(amount: number): void {
  localStorage.setItem(EMD_BALANCE_KEY, String(Math.max(0, amount)));
}

/** Parse first INR amount from emd_summary text. */
export function parseEmdInr(emdSummary?: string | null): number | null {
  if (!emdSummary) return null;
  const m = emdSummary
    .replace(/,/g, "")
    .match(/₹?\s*([\d.]+)\s*(?:lakh|lac|cr|crore)?/i);
  if (!m) return null;
  let n = parseFloat(m[1]);
  if (/lakh|lac/i.test(emdSummary)) n *= 100000;
  if (/crore|cr/i.test(emdSummary)) n *= 10000000;
  return Number.isFinite(n) ? n : null;
}

export function emdEligible(
  emdRequired: number | null,
  balance: number,
): boolean {
  if (emdRequired === null) return true;
  if (balance <= 0) return false;
  return balance >= emdRequired;
}

export function lotsCoverableByBalance(
  emdPerLot: number,
  balance: number,
): number {
  if (emdPerLot <= 0 || balance <= 0) return 0;
  return Math.floor(balance / emdPerLot);
}
