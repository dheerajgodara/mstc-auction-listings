"use client";

import { useMemo, useState } from "react";
import type { AuctionRecord } from "@/types/auction";
import { enrichAuctionDisplay, resolveDisplayTitle } from "@/lib/display-enrichment";
import { auctionDetailPath } from "@/lib/seo/auction-url";
import { formatDateTime, resolvePublicUrl } from "@/lib/utils";
import { loadArchiveAuctionsExport } from "@/lib/load-archive-auctions";

function badgeFor(auction: AuctionRecord): string {
  const reason = String(auction.archive_reason || "");
  if (reason === "under_runway") return "Short window";
  if (reason === "closed") return "Closed";
  if (reason === "aged_out") return "Aged out of live";
  const closing = auction.closing ? Date.parse(auction.closing) : NaN;
  if (!Number.isNaN(closing) && closing < Date.now()) return "Closed";
  return "Archive";
}

function matchesQuery(auction: AuctionRecord, q: string): boolean {
  if (!q) return true;
  const blob = [
    auction.display_title,
    auction.auction_number,
    auction.seller,
    auction.state,
    auction.display_location_city,
    auction.display_location_state,
    auction.display_quantity_summary,
    auction.display_buyer_summary,
    auction.archive_reason,
    ...(auction.lots || []).map((l) => `${l.item_title} ${l.item_description}`),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => blob.includes(token));
}

export function ArchiveClientFilters({ initial }: { initial: AuctionRecord[] }) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [reason, setReason] = useState("all");
  const [live, setLive] = useState<AuctionRecord[] | null>(null);
  const [loading, setLoading] = useState(false);

  const rows = live ?? initial;

  const filtered = useMemo(() => {
    return rows
      .map((a) => enrichAuctionDisplay(a))
      .filter((a) => {
        if (source !== "all" && (a.source || "mstc") !== source) return false;
        if (reason !== "all" && String(a.archive_reason || "") !== reason) return false;
        return matchesQuery(a, query);
      });
  }, [rows, query, source, reason]);

  async function refresh() {
    setLoading(true);
    try {
      const data = await loadArchiveAuctionsExport();
      setLive(data.auctions || []);
    } catch {
      /* keep SSR list */
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex-1 space-y-1 text-body-sm">
          <span className="font-medium text-foreground">Search archive</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Copper, Jodhpur, AIR, auction number…"
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-body text-foreground"
          />
        </label>
        <label className="space-y-1 text-body-sm">
          <span className="font-medium text-foreground">Source</span>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="block w-full rounded-xl border border-border bg-background px-3 py-2"
          >
            <option value="all">All</option>
            <option value="mstc">MSTC</option>
            <option value="gem_forward">GeM Forward</option>
          </select>
        </label>
        <label className="space-y-1 text-body-sm">
          <span className="font-medium text-foreground">Type</span>
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="block w-full rounded-xl border border-border bg-background px-3 py-2"
          >
            <option value="all">All</option>
            <option value="under_runway">Short window</option>
            <option value="closed">Closed</option>
            <option value="aged_out">Aged out</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void refresh()}
          className="btn-secondary rounded-xl px-4 py-2 text-body-sm"
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <p className="text-body-sm text-muted-foreground">
        Showing {filtered.length} of {rows.length} archive auctions (kept ~30 days after close).
      </p>

      <ol className="space-y-4" data-archive-list="true">
        {filtered.map((auction) => {
          const href = resolvePublicUrl(auctionDetailPath(auction).replace(/^\//, ""));
          const name = resolveDisplayTitle(auction);
          const loc = [auction.display_location_city, auction.display_location_state]
            .filter(Boolean)
            .join(", ");
          return (
            <li key={auction.id} className="border-b border-border pb-4">
              <article>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-heading text-foreground">
                    <a href={href} className="link-action">
                      {name}
                    </a>
                  </h2>
                  <span className="rounded-full bg-marketplace-gray-100 px-2 py-0.5 text-caption text-muted-foreground dark:bg-muted">
                    {badgeFor(auction)}
                  </span>
                  {auction.catalogue_status === "ready" ? (
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-caption text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
                      Catalogue
                    </span>
                  ) : null}
                </div>
                <dl className="mt-2 grid gap-1 text-body-sm text-muted-foreground sm:grid-cols-2">
                  {auction.auction_number ? (
                    <div>
                      <dt className="inline font-medium text-foreground">Auction: </dt>
                      <dd className="inline">{auction.auction_number}</dd>
                    </div>
                  ) : null}
                  {loc ? (
                    <div>
                      <dt className="inline font-medium text-foreground">Location: </dt>
                      <dd className="inline">{loc}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt className="inline font-medium text-foreground">Opens: </dt>
                    <dd className="inline tabular-nums">{formatDateTime(auction.opening)}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">Closes: </dt>
                    <dd className="inline tabular-nums">{formatDateTime(auction.closing)}</dd>
                  </div>
                  {auction.display_quantity_summary ? (
                    <div>
                      <dt className="inline font-medium text-foreground">Quantity: </dt>
                      <dd className="inline">{auction.display_quantity_summary}</dd>
                    </div>
                  ) : null}
                  {auction.detail_url ? (
                    <div>
                      <dt className="inline font-medium text-foreground">Official: </dt>
                      <dd className="inline">
                        <a
                          href={auction.detail_url}
                          className="link-action"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Source portal
                        </a>
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </article>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
