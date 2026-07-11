/** Minimal PIN centroid lookup for major industrial hubs (lat, lng). */
const PIN_CENTROIDS: Record<string, [number, number]> = {
  "110001": [28.6139, 77.209],
  "122001": [28.4595, 77.0266],
  "302001": [26.9124, 75.7873],
  "380001": [23.0225, 72.5714],
  "400001": [19.076, 72.8777],
  "411001": [18.5204, 73.8567],
  "560001": [12.9716, 77.5946],
  "600001": [13.0827, 80.2707],
  "201301": [28.5355, 77.391],
  "394210": [21.7051, 72.9956],
};
export function pinToLatLng(pin: string): [number, number] | null {
  const normalized = pin.trim().slice(0, 6);
  if (PIN_CENTROIDS[normalized]) return PIN_CENTROIDS[normalized];
  const prefix3 = normalized.slice(0, 3);
  const match = Object.entries(PIN_CENTROIDS).find(([k]) =>
    k.startsWith(prefix3),
  );
  return match ? match[1] : null;
}
export function haversineKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
} /** Rough city centroids for auctions missing geocode. */
const CITY_COORDS: Record<string, [number, number]> = {
  delhi: [28.6139, 77.209],
  mumbai: [19.076, 72.8777],
  pune: [18.5204, 73.8567],
  bengaluru: [12.9716, 77.5946],
  bangalore: [12.9716, 77.5946],
  chennai: [13.0827, 80.2707],
  ahmedabad: [23.0225, 72.5714],
  jaipur: [26.9124, 75.7873],
  faridabad: [28.4089, 77.3178],
  manesar: [28.35, 76.94],
};
export function auctionLatLng(auction: {
  display_location_city?: string | null;
  display_location_lat?: number | null;
  display_location_lng?: number | null;
}): [number, number] | null {
  if (
    auction.display_location_lat != null &&
    auction.display_location_lng != null
  ) {
    return [auction.display_location_lat, auction.display_location_lng];
  }
  const city = (auction.display_location_city ?? "").toLowerCase();
  for (const [name, coords] of Object.entries(CITY_COORDS)) {
    if (city.includes(name)) return coords;
  }
  return null;
}
export function auctionDistanceKm(
  auction: Parameters<typeof auctionLatLng>[0],
  pin: string,
): number | null {
  const origin = pinToLatLng(pin);
  const dest = auctionLatLng(auction);
  if (!origin || !dest) return null;
  return haversineKm(origin[0], origin[1], dest[0], dest[1]);
}
