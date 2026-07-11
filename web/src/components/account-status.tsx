"use client";

import Link from "next/link";
import { PLAN_CATALOG, type PlanId } from "@/lib/plans";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

export function AccountStatus({ plan }: { plan: PlanId }) {
  const def = PLAN_CATALOG[plan];
  return (
    <div className="surface-elevated p-6">
      <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
        Current plan
      </p>
      <p className="mt-1 text-headline text-foreground">{def.name}</p>
      <p className="text-body-sm text-muted-foreground">{def.tagline}</p>
      <p className="mt-2 tabular-nums text-title text-foreground">
        {def.priceLabel}
        {def.priceInr != null && def.priceInr > 0 && (
          <span className="ml-1 text-footnote font-normal text-muted-foreground">
            / month (hypothesis)
          </span>
        )}
      </p>
      {plan === "free" ? (
        <Link
          href={resolveAppPath("pricing/")}
          className="btn-primary mt-4 inline-flex text-sm"
        >
          Explore paid plans
        </Link>
      ) : (
        <p className="mt-3 text-footnote text-muted-foreground">
          Demo or waitlist status only — live billing is not enabled.
        </p>
      )}
    </div>
  );
}
