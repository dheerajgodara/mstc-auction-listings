"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import { Modal } from "@/components/ui/modal";
import {
  trackCheckoutStartStub,
  trackEnterpriseInquiryClick,
  trackGatedFeatureAttempt,
  trackUpgradeCtaClick,
  trackUpgradePromptView,
} from "@/lib/analytics";
import { startCheckoutStub } from "@/lib/checkout";
import {
  PREMIUM_FEATURES,
  getUpgradePlanForFeature,
  type PremiumFeatureId,
} from "@/lib/entitlements";
import { PLAN_CATALOG, type PlanId } from "@/lib/plans";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

export interface UpgradePromptState {
  open: boolean;
  featureId?: PremiumFeatureId;
  planId?: PlanId;
  source?: string;
}

interface PaywallContextValue {
  prompt: UpgradePromptState;
  showUpgrade: (opts: {
    featureId?: PremiumFeatureId;
    planId?: PlanId;
    source?: string;
  }) => void;
  closeUpgrade: () => void;
  gateFeature: (
    featureId: PremiumFeatureId,
    allowed: boolean,
    source?: string,
  ) => boolean;
}

const PaywallContext = createContext<PaywallContextValue | null>(null);

export function PaywallProvider({ children }: { children: React.ReactNode }) {
  const [prompt, setPrompt] = useState<UpgradePromptState>({ open: false });

  const closeUpgrade = useCallback(() => {
    setPrompt({ open: false });
  }, []);

  const showUpgrade = useCallback(
    (opts: {
      featureId?: PremiumFeatureId;
      planId?: PlanId;
      source?: string;
    }) => {
      const planId =
        opts.planId ??
        (opts.featureId
          ? getUpgradePlanForFeature(opts.featureId)
          : "pro");
      setPrompt({
        open: true,
        featureId: opts.featureId,
        planId,
        source: opts.source,
      });
      trackUpgradePromptView({
        feature: opts.featureId ?? "general",
        plan: planId,
        source: opts.source,
      });
    },
    [],
  );

  const gateFeature = useCallback(
    (featureId: PremiumFeatureId, allowed: boolean, source?: string) => {
      if (allowed) return true;
      trackGatedFeatureAttempt({ feature: featureId, source });
      showUpgrade({ featureId, source });
      return false;
    },
    [showUpgrade],
  );

  const value = useMemo(
    () => ({ prompt, showUpgrade, closeUpgrade, gateFeature }),
    [prompt, showUpgrade, closeUpgrade, gateFeature],
  );

  return (
    <PaywallContext.Provider value={value}>
      {children}
      <UpgradePromptModal />
    </PaywallContext.Provider>
  );
}

export function useUpgradePrompt(): PaywallContextValue {
  const ctx = useContext(PaywallContext);
  if (!ctx) {
    throw new Error("useUpgradePrompt must be used within PaywallProvider");
  }
  return ctx;
}

function UpgradePromptModal() {
  const { prompt, closeUpgrade } = useUpgradePrompt();
  const feature = prompt.featureId
    ? PREMIUM_FEATURES[prompt.featureId]
    : null;
  const planId = prompt.planId ?? "pro";
  const plan = PLAN_CATALOG[planId];

  useEffect(() => {
    if (!prompt.open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeUpgrade();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prompt.open, closeUpgrade]);

  if (!prompt.open) return null;

  const handleSelectPlan = (selected: PlanId) => {
    trackUpgradeCtaClick({
      plan: selected,
      feature: prompt.featureId ?? "general",
      cta: "pricing",
    });
    closeUpgrade();
    window.location.href = resolvePublicUrl(
      `pricing/?plan=${selected}`,
    );
  };

  const handleCheckout = () => {
    trackCheckoutStartStub({ plan: planId });
    const result = startCheckoutStub(planId);
    trackUpgradeCtaClick({
      plan: planId,
      feature: prompt.featureId ?? "general",
      cta: result.ok ? "checkout_stub" : "waitlist",
    });
    closeUpgrade();
    window.location.href = resolvePublicUrl("account/?waitlist=1");
  };

  return (
    <Modal
      open={prompt.open}
      onClose={closeUpgrade}
      title={feature?.title ?? "Upgrade for more buyer tools"}
      className="max-w-md"
    >
      <p className="text-body-sm text-muted-foreground">
        {feature?.reason ??
          "Subscriptions are in early access. Billing is not live yet — review plans and join the waitlist."}
      </p>
      <div className="mt-4 rounded-xl border border-border bg-muted p-4">
        <p className="text-title text-foreground">{plan.name}</p>
        <p className="mt-1 text-body-sm text-muted-foreground">{plan.tagline}</p>
        <p className="mt-2 text-headline tabular-nums text-foreground">
          {plan.priceLabel}
          <span className="ml-1 text-footnote font-normal text-muted-foreground">
            / month (hypothesis)
          </span>
        </p>
      </div>
      <p className="mt-3 text-footnote text-muted-foreground">
        Official MSTC, GeM, and eAuction links stay free. This upgrade unlocks
        workflow tools only — not source verification.
      </p>
      <p className="mt-2 text-footnote text-muted-foreground">
        Payments are not live. Checkout will open after billing provider setup
        and legal review.
      </p>
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={closeUpgrade}>
          Not now
        </button>
        {planId === "enterprise" ? (
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              trackEnterpriseInquiryClick({ source: prompt.source });
              trackUpgradeCtaClick({
                plan: "enterprise",
                feature: prompt.featureId ?? "general",
                cta: "enterprise",
              });
              closeUpgrade();
              window.location.href = resolvePublicUrl("support/");
            }}
          >
            Contact sales
          </button>
        ) : (
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => handleSelectPlan(planId)}
            >
              Compare plans
            </button>
            <button type="button" className="btn-primary" onClick={handleCheckout}>
              Join waitlist
            </button>
          </>
        )}
      </div>
      <p className="mt-4 text-center text-footnote">
        <Link
          href={resolveAppPath("pricing/")}
          className="link-action"
          onClick={() =>
            trackUpgradeCtaClick({
              plan: planId,
              feature: prompt.featureId ?? "general",
              cta: "pricing_link",
            })
          }
        >
          View full pricing
        </Link>
      </p>
    </Modal>
  );
}
