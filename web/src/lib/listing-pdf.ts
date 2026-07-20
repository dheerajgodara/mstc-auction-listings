import type { AuctionRecord } from "@/types/auction";
import { resolvePublicUrl } from "@/lib/utils";

const MEDIA_CDN_HOST =
  (typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_MEDIA_CDN_HOST?.replace(/^https?:\/\//, "").replace(
      /\/$/,
      "",
    )) ||
  "files.csmg.in";

function isCdnMediaUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return u.hostname === MEDIA_CDN_HOST || u.hostname.endsWith(".r2.dev");
  } catch {
    return false;
  }
}

/** Prefer CDN absolute URLs; fall back to relative Hostinger-era asset paths. */
export function listingPdfHref(
  auction: Pick<
    AuctionRecord,
    | "pdf_url"
    | "hostinger_doc_path"
    | "hostinger_doc_url"
    | "document_urls"
  > & { object_doc_url?: string | null },
): string | null {
  const candidates: Array<string | null | undefined> = [
    (auction as { object_doc_url?: string }).object_doc_url,
    auction.pdf_url,
    auction.hostinger_doc_url,
    auction.hostinger_doc_path,
    ...(auction.document_urls ?? []),
  ];

  for (const raw of candidates) {
    if (!raw || typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;

    if (value.startsWith("http://") || value.startsWith("https://")) {
      if (isCdnMediaUrl(value)) return value;
      // Absolute Hostinger auctions/.../pdfs — rewrite to CDN key if possible.
      const auctionsAsset = value.match(/\/auctions\/((?:pdfs|docs)\/[^?#]+)/i);
      if (auctionsAsset) {
        return `https://${MEDIA_CDN_HOST}/${auctionsAsset[1]}`;
      }
      continue;
    }

    // Broken join: .../auctions + pdfs/... => .../auctionspdfs/...
    const broken = value.match(/auctionspdfs\/(.+)$/i);
    if (broken) return `https://${MEDIA_CDN_HOST}/pdfs/${broken[1]}`;

    const relative = value.replace(/^\//, "");
    if (relative.startsWith("pdfs/") || relative.startsWith("docs/")) {
      return `https://${MEDIA_CDN_HOST}/${relative}`;
    }
  }
  return null;
}

/** @deprecated Prefer listingPdfHref — kept for callers that need a relative key. */
export function listingPdfRelativePath(
  auction: Pick<
    AuctionRecord,
    "pdf_url" | "hostinger_doc_path" | "hostinger_doc_url" | "document_urls"
  >,
): string | null {
  const href = listingPdfHref(auction);
  if (!href) return null;
  if (href.startsWith(`https://${MEDIA_CDN_HOST}/`)) {
    return href.slice(`https://${MEDIA_CDN_HOST}/`.length);
  }
  const rel = listingPdfRelativePathLegacy(auction);
  return rel;
}

function listingPdfRelativePathLegacy(
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
    const broken = value.match(/auctionspdfs\/(.+)$/i);
    if (broken) return `pdfs/${broken[1]}`;
    const auctionsAsset = value.match(/\/auctions\/((?:pdfs|docs)\/[^?#]+)/i);
    if (auctionsAsset) return auctionsAsset[1];
    const filesAsset = value.match(
      /files\.scrapauctionindia\.com\/((?:pdfs|docs)\/[^?#]+)/i,
    );
    if (filesAsset) return filesAsset[1];
    const relative = value.replace(/^\//, "");
    if (relative.startsWith("pdfs/") || relative.startsWith("docs/")) {
      return relative;
    }
  }
  return null;
}

/** Resolve a media path or CDN URL for <a href> / <img src>. */
export function resolveMediaUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const relative = path.replace(/^\//, "");
  if (
    relative.startsWith("pdfs/") ||
    relative.startsWith("docs/") ||
    relative.startsWith("thumbs/")
  ) {
    return `https://${MEDIA_CDN_HOST}/${relative}`;
  }
  return resolvePublicUrl(path);
}
