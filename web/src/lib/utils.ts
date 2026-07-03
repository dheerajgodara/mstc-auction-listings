import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "");

/** Resolve public asset URLs for static export under optional basePath (e.g. /auctions). */
export function resolvePublicUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const relative = path.replace(/^\//, "");
  if (BASE_PATH) return `${BASE_PATH}/${relative}`;
  return `/${relative}`;
}

export function formatInr(amount: number | null | undefined): string {
  if (amount == null) return "Price not listed";
  if (amount <= 1) return "Floor price ₹1 (open bidding)";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Kolkata",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatInspection(
  from: string | null | undefined,
  to: string | null | undefined,
  fallback?: string | null,
): string {
  if (from && to) return `${from} – ${to}`;
  return fallback || from || to || "—";
}
