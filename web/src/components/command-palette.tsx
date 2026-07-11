"use client";
import { useEffect, useMemo, useState } from "react";
import { Hash, Search, Star, X } from "lucide-react";
import { Input } from "@/components/ui/primitives";
import { trackEvent } from "@/lib/analytics";
import { loadSavedSearches, type SavedSearch } from "@/lib/saved-searches";
import type { AuctionRecord } from "@/types/auction";
import { cn } from "@/lib/utils";
export function CommandPalette({
  open,
  onClose,
  auctions,
  onSelectAuction,
  onApplySavedSearch,
}: {
  open: boolean;
  onClose: () => void;
  auctions: AuctionRecord[];
  onSelectAuction: (id: string) => void;
  onApplySavedSearch: (search: SavedSearch) => void;
}) {
  const [query, setQuery] = useState("");
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  useEffect(() => {
    if (open) {
      setQuery("");
      setSavedSearches(loadSavedSearches());
      trackEvent("command_palette", { action: "open" });
    }
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  const idMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return auctions
      .filter(
        (a) =>
          a.id.toLowerCase().includes(q) ||
          a.auction_number.toLowerCase().includes(q) ||
          (a.source_auction_id?.toLowerCase().includes(q) ?? false),
      )
      .slice(0, 8);
  }, [auctions, query]);
  const savedMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return savedSearches.slice(0, 6);
    return savedSearches
      .filter(
        (s) =>
          s.name.toLowerCase().includes(q) || s.query.toLowerCase().includes(q),
      )
      .slice(0, 6);
  }, [savedSearches, query]);
  const handleSelectId = (id: string) => {
    trackEvent("command_palette", { action: "jump_to_id", auction_id: id });
    onSelectAuction(id);
    onClose();
  };
  const handleApplySaved = (search: SavedSearch) => {
    trackEvent("command_palette", {
      action: "apply_saved_search",
      search_id: search.id,
    });
    onApplySavedSearch(search);
    onClose();
  };
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {" "}
      <button
        type="button"
        className="absolute inset-0 bg-black/50"
        aria-label="Close command palette"
        onClick={onClose}
      />{" "}
      <div className="absolute left-1/2 top-[12%] w-[min(100%-2rem,32rem)] -translate-x-1/2">
        {" "}
        <div className="surface-elevated overflow-hidden shadow-2xl">
          {" "}
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            {" "}
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" />{" "}
            <Input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Jump to auction ID or saved search…"
              className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0"
              aria-label="Command palette search"
            />{" "}
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary !min-h-[36px] !min-w-[36px] !rounded-full !p-0"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>{" "}
          <div className="max-h-[min(60vh,24rem)] overflow-y-auto p-2">
            {" "}
            {idMatches.length > 0 && (
              <section className="mb-2">
                {" "}
                <p className="px-2 py-1 text-caption font-medium text-muted-foreground">
                  Jump to auction
                </p>
                {idMatches.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => handleSelectId(a.id)}
                    className="flex min-h-[44px] w-full items-start gap-2 rounded-lg px-2 py-2 text-left hover:bg-muted"
                  >
                    {" "}
                    <Hash className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />{" "}
                    <span className="min-w-0">
                      {" "}
                      <span className="block text-sm font-medium text-foreground">
                        {" "}
                        {a.auction_number}{" "}
                      </span>{" "}
                      <span className="line-clamp-1 text-xs text-muted-foreground">
                        {" "}
                        {a.display_title ?? a.item_summary ?? a.id}{" "}
                      </span>{" "}
                    </span>{" "}
                  </button>
                ))}{" "}
              </section>
            )}{" "}
            {savedMatches.length > 0 && (
              <section>
                {" "}
                <p className="px-2 py-1 text-caption font-medium text-muted-foreground">
                  Saved searches
                </p>
                {savedMatches.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => handleApplySaved(s)}
                    className="flex min-h-[44px] w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-muted"
                  >
                    {" "}
                    <Star className="h-4 w-4 shrink-0 text-action" />
                    <span className="min-w-0">
                      {" "}
                      <span className="block text-sm font-medium text-foreground">
                        {s.name}
                      </span>{" "}
                      {s.query && (
                        <span className="line-clamp-1 text-xs text-muted-foreground">
                          {s.query}
                        </span>
                      )}{" "}
                    </span>{" "}
                  </button>
                ))}{" "}
              </section>
            )}{" "}
            {query.trim() &&
              idMatches.length === 0 &&
              savedMatches.length === 0 && (
                <p className="px-2 py-4 text-center text-sm text-muted-foreground">
                  No matches found.
                </p>
              )}{" "}
          </div>{" "}
          <div className="border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
            {" "}
            <kbd className={cn("rounded border border-border bg-card px-1")}>
              Esc
            </kbd>{" "}
            close {" · "}{" "}
            <kbd className="rounded border border-border bg-card px-1">⌘K</kbd>{" "}
            toggle{" "}
          </div>{" "}
        </div>{" "}
      </div>{" "}
    </div>
  );
}
