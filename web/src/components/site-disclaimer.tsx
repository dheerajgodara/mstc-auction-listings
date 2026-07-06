export function SiteDisclaimer({ className = "" }: { className?: string }) {
  return (
    <p
      className={`rounded-lg border border-slate-200/80 bg-slate-50/90 px-3 py-2 text-xs leading-relaxed text-slate-600 ${className}`}
    >
      This portal aggregates public auction listings for discovery only. Always verify
      quantity, location, EMD, and closing details on the official MSTC, GeM, or
      eAuction source before bidding.
    </p>
  );
}
