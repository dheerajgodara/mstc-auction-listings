import type { AuctionSource } from "@/types/auction";
export function sourceRibbonClass(_source?: AuctionSource | null): string {
  return "bg-muted text-muted-foreground";
}
export const SOURCE_LABELS: Record<AuctionSource, string> = {
  mstc: "MSTC",
  eauction: "eAuction",
  gem_forward: "GeM Forward",
};
export function sourceLabel(source?: AuctionSource | null): string {
  const key = source ?? "mstc";
  return SOURCE_LABELS[key] ?? "MSTC";
}
