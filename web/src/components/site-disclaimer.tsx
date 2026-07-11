export function SiteDisclaimer({ className = "" }: { className?: string }) {
  return (
    <p
      className={`text-footnote leading-relaxed text-muted-foreground ${className}`}
    >
      This portal aggregates public auction listings for discovery only. Always
      verify quantity, location, EMD, and closing details on the official MSTC,
      GeM, or eAuction source before bidding.
    </p>
  );
}
