"use client";

import type { AuctionRecord } from "@/types/auction";
import { parseClosingMs } from "@/lib/auction-filters";

const STEPS = [
  "Bid won (verify on source)",
  "STA approval pending",
  "Pay balance (per notice)",
  "Delivery order issued",
  "Gate pass & lifting",
] as const;

export function PostAuctionTracker({ auction }: { auction: AuctionRecord }) {
  const closingMs = parseClosingMs(auction.closing);
  if (closingMs === null || closingMs > Date.now()) return null;

  return (
    <div className="surface-elevated p-4 text-body-sm">
      <p className="mb-3 text-title text-foreground">Post-auction workflow</p>
      <ol className="space-y-1">
        {STEPS.map((step, i) => (
          <li
            key={step}
            className="flex items-center gap-2 text-muted-foreground"
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-card text-[10px] font-bold text-action ring-1 ring-border">
              {i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
      <p className="mt-2 text-footnote text-muted-foreground">
        Informational tracker only — complete all steps on the official source
        portal.
      </p>
    </div>
  );
}
