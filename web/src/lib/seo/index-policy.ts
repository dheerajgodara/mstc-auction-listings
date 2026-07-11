import type { AuctionRecord } from "@/types/auction";
const MS_PER_DAY = 24 * 60 * 60 * 1000;
function parseClosing(closing: string | null | undefined): Date | null {
  if (!closing) return null;
  const date = new Date(closing);
  return Number.isNaN(date.getTime()) ? null : date;
} /** True when closing is in the future or not parseable (treat unknown as active). */
export function isActiveOrUpcomingClosing(
  closing: string | null | undefined,
  now: Date = new Date(),
): boolean {
  const closeDate = parseClosing(closing);
  if (!closeDate) return true;
  return closeDate.getTime() >= now.getTime();
} /** True when the auction closed more than `graceDays` ago. */
export function isExpiredBeyondGrace(
  closing: string | null | undefined,
  now: Date = new Date(),
  graceDays = 30,
): boolean {
  const closeDate = parseClosing(closing);
  if (!closeDate) return false;
  const graceEnd = closeDate.getTime() + graceDays * MS_PER_DAY;
  return now.getTime() > graceEnd;
} /** Whether an auction detail page should be indexed and included in the sitemap. */
export function isIndexableAuction(
  auction: AuctionRecord,
  now: Date = new Date(),
  graceDays = 30,
): boolean {
  return !isExpiredBeyondGrace(auction.closing, now, graceDays);
} /** Landing pages need enough live listings before indexing. */
export function landingPageQualifies(count: number, min = 10): boolean {
  return count >= min;
}
