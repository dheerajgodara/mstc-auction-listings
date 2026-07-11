import { applySortOption } from "@/lib/auction-filters";
import type {
  DiscoveryWorkerRequest,
  DiscoveryWorkerResponse,
} from "@/lib/discovery-worker";
self.onmessage = (event: MessageEvent<DiscoveryWorkerRequest>) => {
  const { auctions, sortBy } = event.data;
  const sorted = applySortOption(auctions, sortBy);
  const response: DiscoveryWorkerResponse = { ids: sorted.map((a) => a.id) };
  self.postMessage(response);
};
