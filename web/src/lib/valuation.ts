import type { AuctionRecord } from "@/types/auction";

export type ValuationStatus =
  | "unknown"
  | "under_market"
  | "fair"
  | "over_market"
  | "not_applicable";

export interface ValuationFields {
  material_type?: string | null;
  estimated_market_value?: number | null;
  valuation_status?: ValuationStatus | null;
  valuation_confidence?: string | null;
  valuation_notes?: string | null;
  benchmark_source?: string | null;
}

export type AuctionWithValuation = AuctionRecord & ValuationFields;

export function getValuationFields(auction: AuctionRecord): ValuationFields {
  const ext = auction as AuctionWithValuation;
  return {
    material_type: ext.material_type ?? auction.asset_category ?? null,
    estimated_market_value: ext.estimated_market_value ?? null,
    valuation_status: ext.valuation_status ?? "unknown",
    valuation_confidence: ext.valuation_confidence ?? null,
    valuation_notes: ext.valuation_notes ?? null,
    benchmark_source: ext.benchmark_source ?? null,
  };
}

export function hasKnownValuation(auction: AuctionRecord): boolean {
  const v = getValuationFields(auction);
  return (
    v.valuation_status != null &&
    v.valuation_status !== "unknown" &&
    v.valuation_status !== "not_applicable" &&
    v.estimated_market_value != null
  );
}

export function valuationBadgeLabel(auction: AuctionRecord): string | null {
  const v = getValuationFields(auction);
  if (!hasKnownValuation(auction)) return null;
  const status = v.valuation_status ?? "unknown";
  const labels: Record<string, string> = {
    under_market: "Below market est.",
    fair: "Fair market est.",
    over_market: "Above market est.",
  };
  return labels[status] ?? null;
}
