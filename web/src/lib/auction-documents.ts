import type { AuctionRecord, LotDocument, LotRecord } from "@/types/auction";

const READY_DOC_STATUSES = new Set(["downloaded", "thumbnail_ready"]);

export function countLotDocuments(lot: LotRecord): number {
  return (lot.documents ?? []).filter(
    (d) => d.cached_url || d.source_url || d.filename,
  ).length;
}

export function countLotPhotos(lot: LotRecord): number {
  const fromDocs = (lot.documents ?? []).filter(
    (d) =>
      d.type === "photo" &&
      (d.thumbnail_url || d.cached_url || d.status === "thumbnail_ready"),
  ).length;
  const previews = lot.preview_images?.length ?? 0;
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
      if (doc.status && READY_DOC_STATUSES.has(doc.status)) hasReady = true;
      if (doc.thumbnail_url) hasReady = true;
    }
  }
  if (auction.pdf_url) {
    documents += 1;
    hasReady = true;
  }
  if ((auction.document_urls?.length ?? 0) > 0) {
    documents += auction.document_urls!.length;
  }
  return { documents, photos, hasReady };
}

export function isBrokenThumbnail(doc: LotDocument): boolean {
  return doc.status === "thumbnail_failed" || doc.status === "failed";
}
