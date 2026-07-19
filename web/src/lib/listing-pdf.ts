import type { AuctionRecord } from "@/types/auction";
import { resolvePublicUrl } from "@/lib/utils";

/** Prefer relative Hostinger asset paths; repair known broken absolute joins. */
export function listingPdfRelativePath(
  auction: Pick<
    AuctionRecord,
    "pdf_url" | "hostinger_doc_path" | "hostinger_doc_url" | "document_urls"
  >,
): string | null {
  const candidates: Array<string | null | undefined> = [
    auction.pdf_url,
    auction.hostinger_doc_path,
    auction.hostinger_doc_url,
    ...(auction.document_urls ?? []),
  ];

  for (const raw of candidates) {
    if (!raw || typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;

    // Broken join: .../auctions + pdfs/... => .../auctionspdfs/...
    const broken = value.match(/auctionspdfs\/(.+)$/i);
    if (broken) return `pdfs/${broken[1]}`;

    const auctionsAsset = value.match(
      /\/auctions\/((?:pdfs|docs)\/[^?#]+)/i,
    );
    if (auctionsAsset) return auctionsAsset[1];

    const relative = value.replace(/^\//, "");
    if (relative.startsWith("pdfs/") || relative.startsWith("docs/")) {
      return relative;
    }
  }
  return null;
}

export function listingPdfHref(
  auction: Pick<
    AuctionRecord,
    "pdf_url" | "hostinger_doc_path" | "hostinger_doc_url" | "document_urls"
  >,
): string | null {
  const rel = listingPdfRelativePath(auction);
  if (!rel) return null;
  return resolvePublicUrl(rel);
}
