import type { PlanId } from "@/lib/plans";

export type CheckoutResult =
  | { ok: true; redirectUrl: string }
  | { ok: false; reason: "disabled" | "not_configured" | "not_implemented" };

/** True only when explicit env flags are set — never by default. */
export function isBillingConfigured(): boolean {
  return (
    process.env.NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED === "true" &&
    Boolean(process.env.NEXT_PUBLIC_BILLING_PROVIDER?.trim())
  );
}

/**
 * Provider-neutral checkout handoff stub.
 * Live billing is intentionally disabled in Anvil Phase 005.
 */
export function startCheckoutStub(planId: PlanId): CheckoutResult {
  if (!isBillingConfigured()) {
    return { ok: false, reason: "not_configured" };
  }
  if (process.env.NEXT_PUBLIC_BILLING_CHECKOUT_ENABLED !== "true") {
    return { ok: false, reason: "disabled" };
  }
  const provider = process.env.NEXT_PUBLIC_BILLING_PROVIDER?.trim();
  if (!provider) {
    return { ok: false, reason: "not_configured" };
  }
  void planId;
  void provider;
  return { ok: false, reason: "not_implemented" };
}
