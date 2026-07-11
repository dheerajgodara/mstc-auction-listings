import type { Metadata } from "next";
import { LegalPageApp } from "@/components/legal-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata: Metadata = {
  title: "Refund policy | Scrap Auction India",
  description: "Refund policy for paid plans (early access draft).",
  ...NOINDEX_METADATA,
};

export default function RefundPolicyPage() {
  return (
    <div className="surface-base min-h-screen">
      <LegalPageApp title="Refund policy">
        <p>
          Billing is not live. This policy will apply when subscriptions launch
          after legal review and provider selection.
        </p>
        <p>
          We expect monthly plans to be cancellable at period end. Pro-rated
          refunds for partial months will be defined in the live checkout terms
          and Indian consumer regulations applicable at launch.
        </p>
        <p>
          Enterprise agreements may include custom refund and SLA terms in a
          signed order form.
        </p>
        <p className="text-footnote">
          Draft for legal review — not final counsel-approved text.
        </p>
      </LegalPageApp>
    </div>
  );
}
