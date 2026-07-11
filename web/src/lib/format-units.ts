/** Format INR with optional unit suffix as non-breaking pair. */
export function formatPriceWithUnit(
  amount: string | number,
  unit?: string | null,
): string {
  const value =
    typeof amount === "number"
      ? new Intl.NumberFormat("en-IN", {
          style: "currency",
          currency: "INR",
          maximumFractionDigits: 0,
        }).format(amount)
      : amount;
  if (!unit?.trim()) return value;
  return `${value}\u00a0/ ${unit.trim()}`;
} /** JSX-friendly span classes for numeric + unit grouping. */
export const UNIT_PAIR_CLASS =
  "inline-flex items-baseline gap-0.5 whitespace-nowrap tabular-nums";
