/** Provider-neutral plan catalog and entitlement keys (Anvil Phase 005). */

export const PLAN_IDS = [
  "free",
  "pro",
  "trader",
  "team",
  "enterprise",
] as const;

export type PlanId = (typeof PLAN_IDS)[number];

export const ENTITLEMENTS = {
  WATCHLIST_EXTENDED: "watchlist_extended",
  SAVED_SEARCHES_EXTENDED: "saved_searches_extended",
  PREMIUM_FILTERS: "premium_filters",
  ADVANCED_DILIGENCE: "advanced_diligence",
  ALERTS: "alerts",
  AI_DEEP_SUMMARY: "ai_deep_summary",
  TEAM_COLLAB: "team_collab",
  ENTERPRISE_SUPPORT: "enterprise_support",
} as const;

export type EntitlementKey = (typeof ENTITLEMENTS)[keyof typeof ENTITLEMENTS];

export interface PlanDefinition {
  id: PlanId;
  name: string;
  tagline: string;
  priceInr: number | null;
  priceLabel: string;
  billingNote: string;
  selfServe: boolean;
  entitlements: readonly EntitlementKey[];
  highlights: readonly string[];
}

export const PLAN_CAPS: Record<
  PlanId,
  { watchlist: number; savedSearches: number }
> = {
  free: { watchlist: 5, savedSearches: 2 },
  pro: { watchlist: 25, savedSearches: 10 },
  trader: { watchlist: 100, savedSearches: 50 },
  team: { watchlist: 250, savedSearches: 100 },
  enterprise: { watchlist: 10_000, savedSearches: 10_000 },
};

const PRO_ENTITLEMENTS: EntitlementKey[] = [
  ENTITLEMENTS.WATCHLIST_EXTENDED,
  ENTITLEMENTS.SAVED_SEARCHES_EXTENDED,
  ENTITLEMENTS.PREMIUM_FILTERS,
];

const TRADER_ENTITLEMENTS: EntitlementKey[] = [
  ...PRO_ENTITLEMENTS,
  ENTITLEMENTS.ADVANCED_DILIGENCE,
  ENTITLEMENTS.ALERTS,
];

const TEAM_ENTITLEMENTS: EntitlementKey[] = [
  ...TRADER_ENTITLEMENTS,
  ENTITLEMENTS.TEAM_COLLAB,
  ENTITLEMENTS.AI_DEEP_SUMMARY,
];

const ENTERPRISE_ENTITLEMENTS: EntitlementKey[] = [
  ...TEAM_ENTITLEMENTS,
  ENTITLEMENTS.ENTERPRISE_SUPPORT,
];

export const PLAN_CATALOG: Record<PlanId, PlanDefinition> = {
  free: {
    id: "free",
    name: "Free",
    tagline: "Trust-building discovery for every buyer",
    priceInr: 0,
    priceLabel: "₹0",
    billingNote: "Always free for public discovery",
    selfServe: true,
    entitlements: [],
    highlights: [
      "Search and filter live listings",
      "Official source and PDF links",
      "Small watchlist and saved searches",
      "Basic diligence preview",
    ],
  },
  pro: {
    id: "pro",
    name: "Pro",
    tagline: "For serious individual traders",
    priceInr: 2999,
    priceLabel: "₹2,999",
    billingNote: "Per month · early-access pricing hypothesis",
    selfServe: true,
    entitlements: PRO_ENTITLEMENTS,
    highlights: [
      "Extended watchlist and saved searches",
      "Premium filters: radius, EMD fit, material tree",
      "Priority upgrade path when billing goes live",
    ],
  },
  trader: {
    id: "trader",
    name: "Trader",
    tagline: "High-frequency buyers and brokers",
    priceInr: 4999,
    priceLabel: "₹4,999",
    billingNote: "Per month · early-access pricing hypothesis",
    selfServe: true,
    entitlements: TRADER_ENTITLEMENTS,
    highlights: [
      "Everything in Pro",
      "Advanced diligence and landed-cost tools",
      "WhatsApp closing reminders",
    ],
  },
  team: {
    id: "team",
    name: "Team",
    tagline: "Small yards and trading desks",
    priceInr: 9999,
    priceLabel: "₹9,999",
    billingNote: "Per month · seats billed when auth ships",
    selfServe: true,
    entitlements: TEAM_ENTITLEMENTS,
    highlights: [
      "Everything in Trader",
      "Shared workflows (when accounts ship)",
      "AI deep summaries when available",
    ],
  },
  enterprise: {
    id: "enterprise",
    name: "Enterprise",
    tagline: "Custom reporting and negotiated support",
    priceInr: 24999,
    priceLabel: "₹24,999+",
    billingNote: "Contact sales · invoice and SLA",
    selfServe: false,
    entitlements: ENTERPRISE_ENTITLEMENTS,
    highlights: [
      "Everything in Team",
      "Controlled export and reporting",
      "Dedicated support channel",
    ],
  },
};

export const ENTITLEMENT_LABELS: Record<
  EntitlementKey,
  { label: string; description: string }
> = {
  [ENTITLEMENTS.WATCHLIST_EXTENDED]: {
    label: "Extended watchlist",
    description: "Track more auctions across closing windows.",
  },
  [ENTITLEMENTS.SAVED_SEARCHES_EXTENDED]: {
    label: "More saved searches",
    description: "Reopen complex filter sets quickly.",
  },
  [ENTITLEMENTS.PREMIUM_FILTERS]: {
    label: "Premium filters",
    description: "Radius, EMD fit, GST slab, and material tree filters.",
  },
  [ENTITLEMENTS.ADVANCED_DILIGENCE]: {
    label: "Advanced diligence",
    description: "Deeper EMD matrix and landed-cost planning.",
  },
  [ENTITLEMENTS.ALERTS]: {
    label: "Closing alerts",
    description: "WhatsApp reminders before auction close.",
  },
  [ENTITLEMENTS.AI_DEEP_SUMMARY]: {
    label: "AI deep summaries",
    description: "Richer AI tags and summaries when enrichment ships.",
  },
  [ENTITLEMENTS.TEAM_COLLAB]: {
    label: "Team collaboration",
    description: "Shared watchlists and seats for small teams.",
  },
  [ENTITLEMENTS.ENTERPRISE_SUPPORT]: {
    label: "Enterprise support",
    description: "Custom onboarding, SLAs, and controlled reporting.",
  },
};

export const REVENUE_TARGET_INR = 300_000;

export function planRank(plan: PlanId): number {
  return PLAN_IDS.indexOf(plan);
}

export function minimumPlanForEntitlement(
  entitlement: EntitlementKey,
): PlanId | null {
  for (const id of PLAN_IDS) {
    if (PLAN_CATALOG[id].entitlements.includes(entitlement)) return id;
  }
  return null;
}
