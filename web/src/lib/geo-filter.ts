import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import type { AuctionRecord } from "@/types/auction";
export interface GeoCoord {
  lat: number;
  lng: number;
}
export type CentroidMap = Record<string, GeoCoord>;
const EARTH_RADIUS_KM = 6371;
function normalizeLookupKey(value: string): string {
  return value.trim().toLowerCase();
}
function lookupCentroid(centroids: CentroidMap, key: string): GeoCoord | null {
  const normalized = normalizeLookupKey(key);
  if (!normalized) return null;
  return centroids[normalized] ?? centroids[key] ?? null;
}
export function haversineDistanceKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_KM * c;
}
export function getAuctionCoords(
  auction: AuctionRecord,
  centroids: CentroidMap,
): GeoCoord | null {
  const display = enrichAuctionDisplay(auction);
  const candidates = [
    display.display_location_city,
    auction.location,
    display.display_location_state,
    auction.state,
    auction.region,
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    const coord = lookupCentroid(centroids, candidate);
    if (coord) return coord;
  }
  return null;
}
export function filterByRadius(
  auctions: AuctionRecord[],
  lat: number,
  lng: number,
  radiusKm: number,
  centroids: CentroidMap,
): AuctionRecord[] {
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || radiusKm <= 0) {
    return auctions;
  }
  return auctions.filter((auction) => {
    const coords = getAuctionCoords(auction, centroids);
    if (!coords) return false;
    return haversineDistanceKm(lat, lng, coords.lat, coords.lng) <= radiusKm;
  });
}
export function distanceToAuctionKm(
  auction: AuctionRecord,
  lat: number,
  lng: number,
  centroids: CentroidMap,
): number | null {
  const coords = getAuctionCoords(auction, centroids);
  if (!coords) return null;
  return haversineDistanceKm(lat, lng, coords.lat, coords.lng);
}
