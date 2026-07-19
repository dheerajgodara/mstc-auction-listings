import type { AuctionRecord, LotDocument, LotRecord } from "@/types/auction";

const READY_DOC_STATUSES = new Set(["downloaded", "thumbnail_ready"]);

function isLocalAssetPath(path: string | null | undefined): boolean {
  if (!path) return false;
  const rel = path.replace(/^\//, "");
  return (
    rel.startsWith("thumbs/") ||
    rel.startsWith("docs/") ||
    rel.startsWith("pdfs/")
  );
}

export function countLotDocuments(lot: LotRecord): number {
  return (lot.documents ?? []).filter(
    (d) => d.cached_url && isLocalAssetPath(d.cached_url),
  ).length;
}

export function countLotPhotos(lot: LotRecord): number {
  const fromDocs = (lot.documents ?? []).filter(
    (d) =>
      d.type === "photo" &&
      d.status === "thumbnail_ready" &&
      d.thumbnail_url &&
      isLocalAssetPath(d.thumbnail_url),
  ).length;
  const previews = (lot.preview_images ?? []).filter((img) => {
    const url = typeof img === "string" ? img : null;
    return url && isLocalAssetPath(url);
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
        ((doc.cached_url && isLocalAssetPath(doc.cached_url)) ||
          (doc.thumbnail_url && isLocalAssetPath(doc.thumbnail_url)))
      ) {
        hasReady = true;
      }
    }
  }
  if (auction.pdf_url && isLocalAssetPath(auction.pdf_url)) {
    documents += 1;
    hasReady = true;
  } else if (auction.hostinger_doc_path && isLocalAssetPath(auction.hostinger_doc_path)) {
    documents += 1;
    hasReady = true;
  }
  if ((auction.document_urls?.length ?? 0) > 0) {
    const localDocs = (auction.document_urls ?? []).filter((u) =>
      isLocalAssetPath(u),
    );
    documents += localDocs.length;
    if (localDocs.length) hasReady = true;
  }
  return { documents, photos, hasReady };
}

export function isBrokenThumbnail(doc: LotDocument): boolean {
  return doc.status === "thumbnail_failed" || doc.status === "failed";
}
