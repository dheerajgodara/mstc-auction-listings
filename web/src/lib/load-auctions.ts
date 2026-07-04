import type { AuctionsExport } from "@/types/auction";
import { resolvePublicUrl } from "@/lib/utils";

declare global {
  interface Window {
    __AUCTIONS_EXPORT__?: AuctionsExport;
  }
}

export interface ExportMeta {
  automation_ran_at: string;
  run_id: string;
  count: number;
  data_version: string;
}

function jsonUrl(): string {
  return resolvePublicUrl("data/auctions.json");
}

function scriptUrl(): string {
  return resolvePublicUrl("data/auctions-data.js");
}

function metaUrl(): string {
  return resolvePublicUrl("data/export-meta.json");
}

function withCacheBust(url: string, version: string): string {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}v=${encodeURIComponent(version)}`;
}

/** Small manifest fetched with no-store so clients never reuse stale auction payloads. */
export async function loadExportMeta(): Promise<ExportMeta | null> {
  try {
    const response = await fetch(metaUrl(), { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as ExportMeta;
  } catch {
    return null;
  }
}

function loadViaScript(version: string): Promise<AuctionsExport> {
  return new Promise((resolve, reject) => {
    const cacheKey = `auctions-data:${version}`;
    const cached = window.__AUCTIONS_EXPORT__;
    if (cached && (cached as AuctionsExport & { __cacheKey?: string }).__cacheKey === cacheKey) {
      resolve(cached);
      return;
    }

    const script = document.createElement("script");
    script.src = withCacheBust(scriptUrl(), version);
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

async function loadViaJson(version: string): Promise<AuctionsExport> {
  const response = await fetch(withCacheBust(jsonUrl(), version), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`auctions.json HTTP ${response.status}`);
  }
  return (await response.json()) as AuctionsExport;
}

/** Load auction export client-side; always bypasses stale CDN/browser caches. */
export async function loadAuctionsExport(): Promise<AuctionsExport> {
  const meta = await loadExportMeta();
  const version =
    meta?.data_version ?? meta?.run_id ?? meta?.automation_ran_at ?? String(Date.now());

  try {
    return await loadViaJson(version);
  } catch {
    return loadViaScript(version);
  }
}
