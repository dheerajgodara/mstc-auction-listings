import type { DailyImportSummaryRow } from "@/types/auction";
import { resolvePublicUrl } from "@/lib/utils";

export async function loadImportHistory(): Promise<DailyImportSummaryRow[]> {
  const url = resolvePublicUrl("data/import-history.json");
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return [];
    const data = (await response.json()) as
      DailyImportSummaryRow[] | { entries?: DailyImportSummaryRow[] };
    return Array.isArray(data) ? data : (data.entries ?? []);
  } catch {
    return [];
  }
}
