/** Local cached listing media only — never MSTC source_url / detail_url. */

import { resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";

export type ListingMediaItem = {
  thumb: string;
  alt: string;
};

function isLocalAssetPath(path: string | null | undefined): boolean {
  if (!path) return false;
  const rel = path.replace(/^\//, "");
  return (
    rel.startsWith("thumbs/") ||
    rel.startsWith("docs/") ||
    rel.startsWith("pdfs/")
  );
}

/** First marketplace photo for listing-card hero. */
export function resolveListingHero(
  auction: AuctionRecord,
): { src: string; alt: string } | null {
  for (const lot of auction.lots ?? []) {
    for (const doc of lot.documents ?? []) {
      if (
        doc.thumbnail_url &&
        doc.status === "thumbnail_ready" &&
        isLocalAssetPath(doc.thumbnail_url)
      ) {
        return {
          src: resolvePublicUrl(doc.thumbnail_url),
          alt: doc.filename || "Auction photo",
        };
      }
    }
  }
  for (const lot of auction.lots ?? []) {
    for (const img of lot.preview_images ?? []) {
      const url =
        typeof img === "string"
          ? img
          : (img as { url?: string; thumbnail_url?: string; src?: string })
              ?.url ||
            (img as { thumbnail_url?: string })?.thumbnail_url ||
            (img as { src?: string })?.src;
      if (url && isLocalAssetPath(url)) {
        return {
          src: resolvePublicUrl(url),
          alt: lot.item_title || "Auction photo",
        };
      }
    }
  }
  return null;
}

export function listingPreviewItems(
  auction: AuctionRecord,
  max = 3,
): ListingMediaItem[] {
  const items: ListingMediaItem[] = [];
  for (const lot of auction.lots ?? []) {
    for (const doc of lot.documents ?? []) {
      if (
        doc.thumbnail_url &&
        doc.status === "thumbnail_ready" &&
        isLocalAssetPath(doc.thumbnail_url)
      ) {
        items.push({
          thumb: resolvePublicUrl(doc.thumbnail_url),
          alt: doc.filename || lot.item_title || "Auction photo",
        });
      }
      if (items.length >= max) return items;
    }
  }
  if (items.length === 0) {
    for (const lot of auction.lots ?? []) {
      for (const img of lot.preview_images ?? []) {
        const url = typeof img === "string" ? img : null;
        if (url && isLocalAssetPath(url)) {
          items.push({
            thumb: resolvePublicUrl(url),
            alt: lot.item_title || "Auction photo",
          });
        }
        if (items.length >= max) return items;
      }
    }
  }
  return items.slice(0, max);
}

export function hasListingPhoto(auction: AuctionRecord): boolean {
  return resolveListingHero(auction) != null;
}
