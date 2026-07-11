"use client";

import Link from "next/link";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { formatCountdown, parseClosingMs } from "@/lib/auction-filters";
import { auctionDetailPath } from "@/lib/seo/auction-url";
import { resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";

function endingThumb(auction: AuctionRecord): string | null {
  for (const lot of auction.lots ?? []) {
    for (const doc of lot.documents ?? []) {
      if (doc.thumbnail_url && doc.status === "thumbnail_ready") {
        return resolvePublicUrl(doc.thumbnail_url);
      }
    }
  }
  return null;
}

export function EndingSoonArena({ auctions }: { auctions: AuctionRecord[] }) {
  const now = Date.now();
  const ending = auctions
    .map((a) => ({ a, ms: parseClosingMs(a.closing) }))
    .filter(
      (x) => x.ms !== null && x.ms > now && x.ms - now <= 2 * 60 * 60 * 1000,
    )
    .sort((x, y) => (x.ms ?? 0) - (y.ms ?? 0))
    .slice(0, 6);
  if (ending.length === 0) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-headline text-foreground">Ending within 2 hours</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ending.map(({ a, ms }) => {
          const e = enrichAuctionDisplay(a);
          const href = resolvePublicUrl(auctionDetailPath(a));
          const thumb = endingThumb(a);
          return (
            <Link
              key={a.id}
              href={href}
              className="surface-elevated overflow-hidden transition-colors hover:border-action"
            >
              <div className="aspect-[20/19] bg-marketplace-gray-100 dark:bg-muted">
                {thumb ? (
                  <img
                    src={thumb}
                    alt=""
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center px-4 text-center text-footnote font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {e.display_material_category ?? e.asset_category ?? "Auction"}
                  </div>
                )}
              </div>
              <div className="p-[var(--space-12)]">
                <p className="line-clamp-2 text-body-sm font-medium text-foreground">
                  {e.display_title ?? e.auction_number}
                </p>
                <p className="mt-1 text-footnote text-muted-foreground">
                  {e.display_material_category ?? e.asset_category}
                </p>
                <div className="mt-2 flex items-center justify-between text-body-sm tabular-nums">
                  <span className="font-semibold text-foreground">
                    {e.price_summary ?? "View listing"}
                  </span>
                  <span className="text-footnote text-muted-foreground">
                    {formatCountdown(ms!)}
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
