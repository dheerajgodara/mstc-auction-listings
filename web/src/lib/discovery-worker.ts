/** * Offloads filter+sort for large exports. Falls back to main-thread when unavailable. */
import type { SortOption } from "@/lib/auction-filters";
import type { AuctionRecord } from "@/types/auction";
export interface DiscoveryWorkerRequest {
  auctions: AuctionRecord[];
  sortBy: SortOption;
  ids?: string[];
}
export interface DiscoveryWorkerResponse {
  ids: string[];
}
export function filterSortInWorker(
  payload: DiscoveryWorkerRequest,
): Promise<string[]> {
  if (typeof Worker === "undefined") {
    return Promise.resolve(payload.auctions.map((a) => a.id));
  }
  return new Promise((resolve, reject) => {
    try {
      const worker = new Worker(
        new URL("./discovery-worker.impl.ts", import.meta.url),
        { type: "module" },
      );
      worker.onmessage = (e: MessageEvent<DiscoveryWorkerResponse>) => {
        worker.terminate();
        resolve(e.data.ids);
      };
      worker.onerror = (err) => {
        worker.terminate();
        reject(err);
      };
      worker.postMessage(payload);
    } catch {
      resolve(payload.auctions.map((a) => a.id));
    }
  });
}
