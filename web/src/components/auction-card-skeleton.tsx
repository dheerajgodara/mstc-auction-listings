import { cn } from "@/lib/utils";

export function AuctionCardSkeleton({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <div
      className="surface-elevated animate-pulse overflow-hidden"
      aria-hidden
    >
      <div className="border-b border-border px-[var(--space-16)] py-[var(--space-12)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-6 w-3/4 rounded bg-muted" />
            <div className="h-4 w-1/2 rounded bg-muted" />
            <div className="flex gap-2">
              <div className="h-5 w-14 rounded-full bg-muted" />
              <div className="h-5 w-16 rounded-full bg-muted" />
            </div>
          </div>
          <div className="h-14 w-24 shrink-0 rounded-xl bg-muted" />
        </div>
      </div>
      <div className="space-y-3 p-[var(--space-16)]">
        <div className="grid grid-cols-2 gap-2">
          <div className="h-4 rounded bg-muted" />
          <div className="h-4 rounded bg-muted" />
          <div className="col-span-2 h-4 rounded bg-muted" />
        </div>
        <div className={cn("h-10 w-28 rounded-full bg-muted", compact && "h-9")} />
      </div>
    </div>
  );
}

export function AuctionTableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="surface-elevated animate-pulse overflow-hidden" aria-hidden>
      <div className="border-b border-border bg-card px-3 py-3">
        <div className="h-4 w-full rounded bg-muted" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3 border-b border-border px-3 py-3">
          <div className="h-4 flex-1 rounded bg-muted" />
          <div className="h-4 w-16 rounded bg-muted" />
          <div className="h-4 w-20 rounded bg-muted" />
          <div className="h-4 w-24 rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}
