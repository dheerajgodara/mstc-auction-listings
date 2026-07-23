import type { AuctionRecord, AuctionsExport } from "@/types/auction";
import { resolvePublicUrl } from "@/lib/utils";

declare global {
  interface Window {
    __ARCHIVE_AUCTIONS_EXPORT__?: AuctionsExport;
  }
}

function jsonUrl(): string {
  return resolvePublicUrl("data/archive-auctions.json");
}

function scriptUrl(): string {
  return resolvePublicUrl("data/archive-auctions-data.js");
}

function withCacheBust(url: string, version: string): string {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}v=${encodeURIComponent(version)}`;
}

function loadViaScript(version: string): Promise<AuctionsExport> {
  return new Promise((resolve, reject) => {
    if (window.__ARCHIVE_AUCTIONS_EXPORT__) {
      resolve(window.__ARCHIVE_AUCTIONS_EXPORT__);
      return;
    }
    const script = document.createElement("script");
    script.src = withCacheBust(scriptUrl(), version);
    script.async = true;
    script.onload = () => {
      if (window.__ARCHIVE_AUCTIONS_EXPORT__) {
        resolve(window.__ARCHIVE_AUCTIONS_EXPORT__);
      } else {
        reject(new Error("archive-auctions-data.js missing __ARCHIVE_AUCTIONS_EXPORT__"));
      }
    };
    script.onerror = () => reject(new Error(`Failed to load ${script.src}`));
    document.head.appendChild(script);
  });
}

async function loadViaJson(version: string): Promise<AuctionsExport> {
  const response = await fetch(withCacheBust(jsonUrl(), version), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`archive-auctions.json HTTP ${response.status}`);
  }
  return (await response.json()) as AuctionsExport;
}

/** Client loader for T-30 archive export. */
export async function loadArchiveAuctionsExport(): Promise<AuctionsExport> {
  const version = String(Date.now());
  try {
    return await loadViaJson(version);
  } catch {
    return loadViaScript(version);
  }
}

export type ArchiveAuction = AuctionRecord;
