import {
  ENTITLEMENTS,
  PLAN_CAPS,
  PLAN_CATALOG,
  PLAN_IDS,
  type EntitlementKey,
  type PlanId,
  planRank,
} from "@/lib/plans";

const DEMO_PLAN_STORAGE_KEY = "mstc_paywall_demo_plan_v1";

export type PremiumFeatureId =
  | "watchlist_add"
  | "saved_search_save"
  | "filter_geo_radius"
  | "filter_emd_eligible"
  | "filter_material_tree"
  | "filter_gst_slab"
  | "filter_large_lots"
  | "diligence_advanced"
  | "whatsapp_alert"
  | "ai_deep_summary";

export interface PremiumFeatureMeta {
  id: PremiumFeatureId;
  title: string;
  reason: string;
  entitlement: EntitlementKey;
  minimumPlan: PlanId;
}

export const PREMIUM_FEATURES: Record<PremiumFeatureId, PremiumFeatureMeta> = {
  watchlist_add: {
    id: "watchlist_add",
    title: "Watchlist limit reached",
    reason:
      "Free buyers can star a few auctions. Upgrade for a larger watchlist.",
    entitlement: ENTITLEMENTS.WATCHLIST_EXTENDED,
    minimumPlan: "pro",
  },
  saved_search_save: {
    id: "saved_search_save",
    title: "Saved search limit reached",
    reason:
      "Save more filter combinations and reopen them from Discover.",
    entitlement: ENTITLEMENTS.SAVED_SEARCHES_EXTENDED,
    minimumPlan: "pro",
  },
  filter_geo_radius: {
    id: "filter_geo_radius",
    title: "Radius filter",
    reason: "Filter yards within a PIN code radius for logistics planning.",
    entitlement: ENTITLEMENTS.PREMIUM_FILTERS,
    minimumPlan: "pro",
  },
  filter_emd_eligible: {
    id: "filter_emd_eligible",
    title: "EMD-fit filter",
    reason: "Show only lots your EMD balance can cover.",
    entitlement: ENTITLEMENTS.PREMIUM_FILTERS,
    minimumPlan: "pro",
  },
  filter_material_tree: {
    id: "filter_material_tree",
    title: "Material tree filter",
    reason: "Target specific scrap grades in the taxonomy tree.",
    entitlement: ENTITLEMENTS.PREMIUM_FILTERS,
    minimumPlan: "pro",
  },
  filter_gst_slab: {
    id: "filter_gst_slab",
    title: "GST slab filter",
    reason: "Narrow listings by GST rate for landed-cost planning.",
    entitlement: ENTITLEMENTS.PREMIUM_FILTERS,
    minimumPlan: "pro",
  },
  filter_large_lots: {
    id: "filter_large_lots",
    title: "Large-lot filter",
    reason: "Surface high-tonnage opportunities faster.",
    entitlement: ENTITLEMENTS.PREMIUM_FILTERS,
    minimumPlan: "pro",
  },
  diligence_advanced: {
    id: "diligence_advanced",
    title: "Advanced diligence",
    reason:
      "Unlock deeper EMD matrix and adjustable landed-cost assumptions.",
    entitlement: ENTITLEMENTS.ADVANCED_DILIGENCE,
    minimumPlan: "trader",
  },
  whatsapp_alert: {
    id: "whatsapp_alert",
    title: "Closing reminders",
    reason: "Get a WhatsApp reminder before an auction closes.",
    entitlement: ENTITLEMENTS.ALERTS,
    minimumPlan: "trader",
  },
  ai_deep_summary: {
    id: "ai_deep_summary",
    title: "AI deep summary",
    reason: "Read full AI-enriched summaries when available.",
    entitlement: ENTITLEMENTS.AI_DEEP_SUMMARY,
    minimumPlan: "team",
  },
};

export function isDemoPlanModeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_PAYWALL_DEMO_MODE === "true";
}

export function loadDemoPlanOverride(): PlanId | null {
  if (!isDemoPlanModeEnabled() || typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DEMO_PLAN_STORAGE_KEY);
    if (!raw) return null;
    if (!PLAN_IDS.includes(raw as PlanId)) return null;
    return raw as PlanId;
  } catch {
    return null;
  }
}

export function saveDemoPlanOverride(plan: PlanId | null): void {
  if (!isDemoPlanModeEnabled() || typeof window === "undefined") return;
  if (!plan || plan === "free") {
    localStorage.removeItem(DEMO_PLAN_STORAGE_KEY);
    return;
  }
  localStorage.setItem(DEMO_PLAN_STORAGE_KEY, plan);
}

export function getCurrentPlan(): PlanId {
  const demo = loadDemoPlanOverride();
  return demo ?? "free";
}

export function hasEntitlement(
  entitlement: EntitlementKey,
  plan: PlanId = getCurrentPlan(),
): boolean {
  return PLAN_CATALOG[plan].entitlements.includes(entitlement);
}

export function getPlanCaps(plan: PlanId = getCurrentPlan()) {
  return PLAN_CAPS[plan];
}

export function canAddWatchlist(
  currentCount: number,
  plan: PlanId = getCurrentPlan(),
): boolean {
  return currentCount < PLAN_CAPS[plan].watchlist;
}

export function canSaveSearch(
  currentCount: number,
  plan: PlanId = getCurrentPlan(),
): boolean {
  return currentCount < PLAN_CAPS[plan].savedSearches;
}

export function canUsePremiumFeature(
  featureId: PremiumFeatureId,
  plan: PlanId = getCurrentPlan(),
): boolean {
  const meta = PREMIUM_FEATURES[featureId];
  return hasEntitlement(meta.entitlement, plan);
}

export function planMeetsMinimum(
  current: PlanId,
  required: PlanId,
): boolean {
  return planRank(current) >= planRank(required);
}

export function getUpgradePlanForFeature(
  featureId: PremiumFeatureId,
): PlanId {
  return PREMIUM_FEATURES[featureId].minimumPlan;
}
