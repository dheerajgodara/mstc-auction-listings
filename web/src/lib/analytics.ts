declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

const MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();

/** Canonical GA4 custom event names (low-cardinality params only). */
export const ANALYTICS_EVENTS = {
  PAGE_VIEW: "page_view",
  VIEW_AUCTION_DETAIL: "view_auction_detail",
  VIEW_LANDING: "view_landing",
  SEARCH: "search",
  FILTER_CHANGE: "filter_change",
  SORT_CHANGE: "sort_change",
  NO_RESULTS: "no_results",
  PDF_OPEN: "pdf_open",
  SOURCE_OPEN: "source_open",
  LOT_EXPAND: "lot_expand",
  WATCHLIST_TOGGLE: "watchlist_toggle",
  SAVED_SEARCH_APPLY: "apply_saved_search",
  SAVED_SEARCH_SAVE: "saved_search_save",
  DILIGENCE_OPEN: "diligence_open",
  COMPARE_ADD: "compare_add",
  COMPARE_REMOVE: "compare_remove",
  MAP_VIEW: "map_view",
  MAP_SELECT: "map_select",
  COMMAND_PALETTE: "command_palette",
  STATUS_PAGE_VIEW: "status_page_view",
  PRICING_PAGE_VIEW: "pricing_page_view",
  PLAN_SELECT: "plan_select",
  UPGRADE_PROMPT_VIEW: "upgrade_prompt_view",
  UPGRADE_CTA_CLICK: "upgrade_cta_click",
  GATED_FEATURE_ATTEMPT: "gated_feature_attempt",
  CHECKOUT_START_STUB: "checkout_start_stub",
  ENTERPRISE_INQUIRY_CLICK: "enterprise_inquiry_click",
  ACCOUNT_PAGE_VIEW: "account_page_view",
  LAUNCH_READINESS_PAGE_VIEW: "launch_readiness_page_view",
  APP_PAGE_VIEW: "app_page_view",
  APP_INSTALL_CLICK: "app_install_click",
} as const;

export type AnalyticsEventName =
  (typeof ANALYTICS_EVENTS)[keyof typeof ANALYTICS_EVENTS];

export function isAnalyticsEnabled(): boolean {
  return Boolean(MEASUREMENT_ID);
}

export function trackEvent(
  name: AnalyticsEventName | string,
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
  trackEvent(ANALYTICS_EVENTS.PAGE_VIEW, { page_path: path });
}

export function trackDetailPageView(auctionId: string, source?: string): void {
  trackEvent(ANALYTICS_EVENTS.VIEW_AUCTION_DETAIL, {
    auction_id: auctionId,
    source: source ?? "unknown",
  });
}

export function trackLandingPageView(landingSlug: string): void {
  trackEvent(ANALYTICS_EVENTS.VIEW_LANDING, { landing_slug: landingSlug });
}

export function trackSearch(searchTerm: string): void {
  trackEvent(ANALYTICS_EVENTS.SEARCH, {
    search_term: searchTerm.slice(0, 100),
  });
}

export function trackFilterChange(activeFilterCount: number): void {
  trackEvent(ANALYTICS_EVENTS.FILTER_CHANGE, {
    active_filters: activeFilterCount,
  });
}

export function trackSortChange(sort: string): void {
  trackEvent(ANALYTICS_EVENTS.SORT_CHANGE, { sort });
}

export function trackNoResults(hasQuery: boolean, filterCount: number): void {
  trackEvent(ANALYTICS_EVENTS.NO_RESULTS, {
    has_query: hasQuery,
    filter_count: filterCount,
  });
}

export function trackDiligenceOpen(auctionId: string): void {
  trackEvent(ANALYTICS_EVENTS.DILIGENCE_OPEN, { auction_id: auctionId });
}

export function trackCompareAdd(auctionId: string, compareCount: number): void {
  trackEvent(ANALYTICS_EVENTS.COMPARE_ADD, {
    auction_id: auctionId,
    compare_count: compareCount,
  });
}

export function trackCompareRemove(auctionId: string, compareCount: number): void {
  trackEvent(ANALYTICS_EVENTS.COMPARE_REMOVE, {
    auction_id: auctionId,
    compare_count: compareCount,
  });
}

export function trackMapSelect(city: string): void {
  trackEvent(ANALYTICS_EVENTS.MAP_SELECT, {
    city: city.slice(0, 80),
  });
}

export function trackPricingPageView(): void {
  trackEvent(ANALYTICS_EVENTS.PRICING_PAGE_VIEW);
}

export function trackPlanSelect(plan: string): void {
  trackEvent(ANALYTICS_EVENTS.PLAN_SELECT, { plan });
}

export function trackUpgradePromptView(params: {
  feature: string;
  plan: string;
  source?: string;
}): void {
  trackEvent(ANALYTICS_EVENTS.UPGRADE_PROMPT_VIEW, {
    feature: params.feature,
    plan: params.plan,
    source: params.source ?? "unknown",
  });
}

export function trackUpgradeCtaClick(params: {
  plan: string;
  feature: string;
  cta: string;
}): void {
  trackEvent(ANALYTICS_EVENTS.UPGRADE_CTA_CLICK, {
    plan: params.plan,
    feature: params.feature,
    cta: params.cta,
  });
}

export function trackGatedFeatureAttempt(params: {
  feature: string;
  source?: string;
}): void {
  trackEvent(ANALYTICS_EVENTS.GATED_FEATURE_ATTEMPT, {
    feature: params.feature,
    source: params.source ?? "unknown",
  });
}

export function trackCheckoutStartStub(params: { plan: string }): void {
  trackEvent(ANALYTICS_EVENTS.CHECKOUT_START_STUB, { plan: params.plan });
}

export function trackEnterpriseInquiryClick(params?: {
  source?: string;
}): void {
  trackEvent(ANALYTICS_EVENTS.ENTERPRISE_INQUIRY_CLICK, {
    source: params?.source ?? "unknown",
  });
}

export function trackAccountPageView(): void {
  trackEvent(ANALYTICS_EVENTS.ACCOUNT_PAGE_VIEW);
}

export function trackLaunchReadinessPageView(): void {
  trackEvent(ANALYTICS_EVENTS.LAUNCH_READINESS_PAGE_VIEW);
}

export function trackAppPageView(): void {
  trackEvent(ANALYTICS_EVENTS.APP_PAGE_VIEW);
}

export function trackAppInstallClick(method: string): void {
  trackEvent(ANALYTICS_EVENTS.APP_INSTALL_CLICK, { method });
}

export const GA_MEASUREMENT_ID = MEASUREMENT_ID;
