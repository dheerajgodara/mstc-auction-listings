declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

const MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();

export function isAnalyticsEnabled(): boolean {
  return Boolean(MEASUREMENT_ID);
}

export function trackEvent(
  name: string,
  params?: Record<string, string | number | boolean | undefined>,
): void {
  if (typeof window === "undefined" || !window.gtag || !MEASUREMENT_ID) return;
  const clean: Record<string, string | number | boolean> = {};
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) clean[k] = v;
    }
  }
  window.gtag("event", name, clean);
}

export function trackPageView(path: string): void {
  if (!MEASUREMENT_ID) return;
  trackEvent("page_view", { page_path: path });
}

export const GA_MEASUREMENT_ID = MEASUREMENT_ID;
