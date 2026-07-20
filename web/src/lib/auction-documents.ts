import type { AuctionRecord, LotDocument, LotRecord } from "@/types/auction";

const READY_DOC_STATUSES = new Set(["downloaded", "thumbnail_ready"]);
const MEDIA_CDN_HOST =
  (typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_MEDIA_CDN_HOST?.replace(/^https?:\/\//, "").replace(
      /\/$/,
      "",
    )) ||
  "files.csmg.in";

/** True for CDN absolute URLs or relative pdfs/docs/thumbs keys. */
export function isMediaAssetPath(path: string | null | undefined): boolean {
  if (!path) return false;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    try {
      const u = new URL(path);
      return (
        u.hostname === MEDIA_CDN_HOST ||
        u.hostname.endsWith(".r2.dev") ||
        /\/(?:pdfs|docs|thumbs)\//.test(u.pathname)
      );
    } catch {
      return false;
    }
  }
  const rel = path.replace(/^\//, "");
  return (
    rel.startsWith("thumbs/") ||
    rel.startsWith("docs/") ||
    rel.startsWith("pdfs/")
  );
}

/** @deprecated use isMediaAssetPath */
function isLocalAssetPath(path: string | null | undefined): boolean {
  return isMediaAssetPath(path);
}

export function countLotDocuments(lot: LotRecord): number {
  return (lot.documents ?? []).filter(
    (d) => d.cached_url && isMediaAssetPath(d.cached_url),
  ).length;
}

export function countLotPhotos(lot: LotRecord): number {
  const fromDocs = (lot.documents ?? []).filter(
    (d) =>
      d.type === "photo" &&
      d.status === "thumbnail_ready" &&
      d.thumbnail_url &&
      isMediaAssetPath(d.thumbnail_url),
  ).length;
  const previews = (lot.preview_images ?? []).filter((img) => {
    const url = typeof img === "string" ? img : null;
    return url && isMediaAssetPath(url);
  }).length;
  return Math.max(fromDocs, previews > 0 ? previews : 0);
}

export function countAuctionDocuments(auction: AuctionRecord): {
  documents: number;
  photos: number;
  hasReady: boolean;
} {
  let documents = 0;
  let photos = 0;
  let hasReady = false;
  for (const lot of auction.lots ?? []) {
    documents += countLotDocuments(lot);
    photos += countLotPhotos(lot);
    for (const doc of lot.documents ?? []) {
      if (
        doc.status &&
        READY_DOC_STATUSES.has(doc.status) &&
        ((doc.cached_url && isMediaAssetPath(doc.cached_url)) ||
          (doc.thumbnail_url && isMediaAssetPath(doc.thumbnail_url)))
      ) {
        hasReady = true;
      }
    }
  }
  if (auction.pdf_url && isMediaAssetPath(auction.pdf_url)) {
    documents += 1;
    hasReady = true;
  } else if (
    auction.hostinger_doc_path &&
    isMediaAssetPath(auction.hostinger_doc_path)
  ) {
    documents += 1;
    hasReady = true;
  }
  if ((auction.document_urls?.length ?? 0) > 0) {
    const localDocs = (auction.document_urls ?? []).filter((u) =>
      isMediaAssetPath(u),
    );
    documents += localDocs.length;
    if (localDocs.length) hasReady = true;
  }
  return { documents, photos, hasReady };
}

export function isBrokenThumbnail(doc: LotDocument): boolean {
  return doc.status === "thumbnail_failed" || doc.status === "failed";
}

// Keep unused helper referenced for older imports that may tree-shake oddly.
void isLocalAssetPath;
