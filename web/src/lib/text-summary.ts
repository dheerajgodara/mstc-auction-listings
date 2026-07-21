/** Compact card summary — full text belongs in expanded details. */
export function truncateSummary(
  text: string | null | undefined,
  maxLen = 160,
): string {
  return truncateAtSentence(text, maxLen);
}

/** Prefer ending on a sentence boundary so catalogue prose is not cut mid-thought. */
export function truncateAtSentence(
  text: string | null | undefined,
  maxLen = 600,
): string {
  const clean = (text ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return "—";
  if (clean.length <= maxLen) return clean;
  const slice = clean.slice(0, maxLen);
  const sentenceEnd = Math.max(
    slice.lastIndexOf(". "),
    slice.lastIndexOf("! "),
    slice.lastIndexOf("? "),
  );
  if (sentenceEnd >= Math.floor(maxLen * 0.4)) {
    return slice.slice(0, sentenceEnd + 1).trim();
  }
  const space = slice.lastIndexOf(" ");
  const cut = space > Math.floor(maxLen * 0.5) ? slice.slice(0, space) : slice;
  return `${cut.trimEnd()}…`;
}

export function isLongSummary(
  text: string | null | undefined,
  threshold = 200,
): boolean {
  return (text ?? "").trim().length > threshold;
}

/** Notice / what’s-being-sold body for detail pages. */
export function resolveNoticeBody(auction: {
  item_summary?: string | null;
  display_title?: string | null;
  lots?: Array<{
    lot_description_text?: string | null;
    item_description?: string | null;
  }>;
}): string | null {
  const summary = (auction.item_summary ?? "").trim();
  const title = (auction.display_title ?? "").trim();
  if (summary && summary !== title && summary.length >= 40) {
    return summary;
  }
  const lots = auction.lots ?? [];
  for (const lot of lots) {
    const desc = (
      lot.lot_description_text ||
      lot.item_description ||
      ""
    ).trim();
    if (desc && desc.length >= 20) return desc;
  }
  if (summary && summary !== title) return summary;
  return null;
}
