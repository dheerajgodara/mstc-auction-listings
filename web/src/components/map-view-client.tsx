"use client";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { trackMapSelect } from "@/lib/analytics";
import { getAuctionCoords, type CentroidMap } from "@/lib/geo-filter";
import { resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
import { cn } from "@/lib/utils";
interface CityCluster {
  key: string;
  city: string;
  lat: number;
  lng: number;
  count: number;
  auctions: AuctionRecord[];
}
function clusterIcon(count: number) {
  const size = count > 50 ? 44 : count > 10 ? 38 : 32;
  return L.divIcon({
    className: "",
    html: `<div style=" width:${size}px;height:${size}px; display:flex;align-items:center;justify-content:center; border-radius:9999px; background:linear-gradient(135deg,#FF385C,#E00B41); color:white;font-weight:700;font-size:12px; border:2px solid rgba(255,255,255,0.95); box-shadow:0 8px 24px rgba(224,11,65,0.35); ">${count}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}
function buildClusters(
  auctions: AuctionRecord[],
  centroids: CentroidMap,
): CityCluster[] {
  const map = new Map<string, CityCluster>();
  for (const auction of auctions) {
    const display = enrichAuctionDisplay(auction);
    const city = display.display_location_city;
    if (!city) continue;
    const coords = getAuctionCoords(auction, centroids);
    if (!coords) continue;
    const key = city.toLowerCase();
    const existing = map.get(key);
    if (existing) {
      existing.count += 1;
      existing.auctions.push(auction);
    } else {
      map.set(key, {
        key,
        city,
        lat: coords.lat,
        lng: coords.lng,
        count: 1,
        auctions: [auction],
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.count - a.count);
}
export function MapViewClient({
  auctions,
  onSelectAuction,
  className,
}: {
  auctions: AuctionRecord[];
  onSelectAuction?: (id: string) => void;
  className?: string;
}) {
  const [centroids, setCentroids] = useState<CentroidMap>({});
  const [cssReady, setCssReady] = useState(false);
  useEffect(() => {
    const href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    const existing = document.querySelector(`link[href="${href}"]`);
    if (existing) {
      setCssReady(true);
      return;
    }
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.onload = () => setCssReady(true);
    link.onerror = () => setCssReady(true);
    document.head.appendChild(link);
  }, []);
  useEffect(() => {
    let cancelled = false;
    fetch(resolvePublicUrl("data/city-centroids.json"))
      .then((r) => r.json())
      .then((data: CentroidMap) => {
        if (!cancelled) setCentroids(data);
      })
      .catch(() => {
        if (!cancelled) setCentroids({});
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const clusters = useMemo(
    () => buildClusters(auctions, centroids),
    [auctions, centroids],
  );
  const center = useMemo<[number, number]>(() => {
    if (clusters.length === 0) return [22.5, 79];
    const lat = clusters.reduce((s, c) => s + c.lat, 0) / clusters.length;
    const lng = clusters.reduce((s, c) => s + c.lng, 0) / clusters.length;
    return [lat, lng];
  }, [clusters]);
  if (!cssReady) {
    return (
      <div
        className={cn(
          "surface-elevated flex h-[480px] items-center justify-center",
          className,
        )}
      >
        {" "}
        <p className="text-sm text-muted-foreground">Loading map…</p>{" "}
      </div>
    );
  }
  return (
    <div className={cn("surface-elevated overflow-hidden", className)}>
      {" "}
      <MapContainer
        center={center}
        zoom={5}
        scrollWheelZoom
        className="h-[min(70vh,560px)] w-full"
        aria-label="Auction locations map"
      >
        {" "}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />{" "}
        {clusters.map((cluster) => (
          <Marker
            key={cluster.key}
            position={[cluster.lat, cluster.lng]}
            icon={clusterIcon(cluster.count)}
          >
            {" "}
            <Popup>
              {" "}
              <div className="space-y-2 p-1">
                {" "}
                <p className="font-semibold text-foreground">
                  {" "}
                  {cluster.city} ({cluster.count}){" "}
                </p>{" "}
                <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
                  {" "}
                  {cluster.auctions.slice(0, 8).map((a) => {
                    const title =
                      a.display_title ?? a.item_summary ?? a.auction_number;
                    return (
                      <li key={a.id}>
                        {" "}
                        {onSelectAuction ? (
                          <button
                            type="button"
                            onClick={() => {
                              trackMapSelect(cluster.city);
                              onSelectAuction(a.id);
                            }}
                            className="text-left link-action"
                          >
                            {" "}
                            {title}{" "}
                          </button>
                        ) : (
                          <span>{title}</span>
                        )}{" "}
                      </li>
                    );
                  })}{" "}
                </ul>{" "}
                {cluster.auctions.length > 8 && (
                  <p className="text-[11px] text-muted-foreground">
                    {" "}
                    +{cluster.auctions.length - 8} more{" "}
                  </p>
                )}{" "}
              </div>{" "}
            </Popup>{" "}
          </Marker>
        ))}{" "}
      </MapContainer>{" "}
      {clusters.length === 0 && (
        <p className="border-t border-border px-4 py-3 text-center text-sm text-muted-foreground">
          {" "}
          No geocoded auction locations to display.{" "}
        </p>
      )}{" "}
    </div>
  );
}
