"use client";
import { Info } from "lucide-react";
import { formatInr } from "@/lib/utils";
import type { LotRecord } from "@/types/auction";
export function LandedCostEstimator({
  basePriceInr,
  quantityMt = 1,
  gstPercent = 18,
  tcsPercent = 1,
  buyerPremiumPercent = 1,
}: {
  basePriceInr: number;
  quantityMt?: number;
  gstPercent?: number;
  tcsPercent?: number;
  buyerPremiumPercent?: number;
}) {
  const premium = basePriceInr * (buyerPremiumPercent / 100);
  const subtotal = basePriceInr + premium;
  const gst = subtotal * (gstPercent / 100);
  const tcs = subtotal * (tcsPercent / 100);
  const perMt = subtotal + gst + tcs;
  const total = perMt * quantityMt;
  return (
    <div className="surface-elevated p-4 text-body-sm">
      <div className="mb-3 flex items-center gap-2 text-title text-foreground">
        <Info className="h-4 w-4 shrink-0 text-muted-foreground" />
        Landed cost estimate (ex-freight)
      </div>
      <dl className="space-y-1.5 tabular-nums">
        {" "}
        <div className="flex justify-between">
          {" "}
          <dt>Base bid / MT</dt> <dd>{formatInr(basePriceInr)}</dd>{" "}
        </div>{" "}
        <div className="flex justify-between text-muted-foreground">
          {" "}
          <dt>Buyer premium ({buyerPremiumPercent}%)</dt>{" "}
          <dd>{formatInr(premium)}</dd>{" "}
        </div>{" "}
        <div className="flex justify-between text-muted-foreground">
          {" "}
          <dt>GST ({gstPercent}%)</dt> <dd>{formatInr(gst)}</dd>{" "}
        </div>{" "}
        <div className="flex justify-between text-muted-foreground">
          {" "}
          <dt>TCS ({tcsPercent}%)</dt> <dd>{formatInr(tcs)}</dd>{" "}
        </div>{" "}
        <div className="flex justify-between border-t border-border pt-2 font-medium text-foreground">
          <dt>Effective / MT</dt>
          <dd>{formatInr(perMt)}</dd>
        </div>
        {quantityMt > 1 && (
          <div className="flex justify-between font-medium text-foreground">
            <dt>Total ({quantityMt} MT)</dt>
            <dd>{formatInr(total)}</dd>
          </div>
        )}
      </dl>
      <p className="mt-3 text-footnote text-muted-foreground">
        Estimates for diligence only — official source terms prevail. Excludes
        freight, lifting, and weighbridge deductions.
      </p>
    </div>
  );
}
export function parseGstPercent(lot?: LotRecord): number {
  const g = lot?.gst ?? "";
  const m = g.match(/(\d+)\s*%/);
  return m ? Number(m[1]) : 18;
}
