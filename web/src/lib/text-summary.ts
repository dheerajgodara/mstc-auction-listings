/** Compact card summary — full text belongs in expanded details. */
export function truncateSummary(text: string | null | undefined, maxLen = 160): string {
  const clean = (text ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return "—";
  if (clean.length <= maxLen) return clean;
  return `${clean.slice(0, maxLen - 1).trimEnd()}…`;
}

export function isLongSummary(text: string | null | undefined, threshold = 200): boolean {
  return (text ?? "").trim().length > threshold;
}
