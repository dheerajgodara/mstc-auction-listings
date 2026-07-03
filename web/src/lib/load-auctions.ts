import type { AuctionsExport } from "@/types/auction";
import { resolvePublicUrl } from "@/lib/utils";

declare global {
  interface Window {
    __AUCTIONS_EXPORT__?: AuctionsExport;
  }
}

function scriptUrl(): string {
  return resolvePublicUrl("data/auctions-data.js");
}

function jsonUrl(): string {
  return resolvePublicUrl("data/auctions.json");
}

function loadViaScript(): Promise<AuctionsExport> {
  return new Promise((resolve, reject) => {
    if (window.__AUCTIONS_EXPORT__) {
      resolve(window.__AUCTIONS_EXPORT__);
      return;
    }
    const script = document.createElement("script");
    script.src = scriptUrl();
    script.async = true;
    script.onload = () => {
      if (window.__AUCTIONS_EXPORT__) {
        resolve(window.__AUCTIONS_EXPORT__);
      } else {
        reject(new Error("auctions-data.js loaded without __AUCTIONS_EXPORT__"));
      }
    };
    script.onerror = () => reject(new Error(`Failed to load ${script.src}`));
    document.head.appendChild(script);
  });
}

async function loadViaJson(): Promise<AuctionsExport> {
  const response = await fetch(jsonUrl(), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`auctions.json HTTP ${response.status}`);
  }
  return (await response.json()) as AuctionsExport;
}

/** Load auction export client-side (Hostinger-safe .js with JSON fallback). */
export async function loadAuctionsExport(): Promise<AuctionsExport> {
  try {
    return await loadViaScript();
  } catch {
    return loadViaJson();
  }
}
