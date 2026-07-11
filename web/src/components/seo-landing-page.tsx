"use client";
import Link from "next/link";
import { useEffect } from "react";
import { AuctionDiscoveryView } from "@/components/auction-discovery-view";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { trackLandingPageView } from "@/lib/analytics";
import { enrichAuctions } from "@/lib/display-enrichment";
import { SITE_BASE_URL } from "@/lib/site-url";
import type { AuctionRecord } from "@/types/auction";

export function SeoLandingPage({
  title,
  description,
  intro,
  auctions,
  topLinks,
  landingSlug,
}: {
  title: string;
  description: string;
  intro: string;
  auctions: AuctionRecord[];
  topLinks?: { label: string; href: string }[];
  landingSlug?: string;
}) {
  const enriched = enrichAuctions(auctions);
  useEffect(() => {
    if (landingSlug) trackLandingPageView(landingSlug);
  }, [landingSlug]);
  return (
    <AppShell>
      <main className="py-section">
        <div className="container-marketplace mb-8 space-y-5">
          <Link href={SITE_BASE_URL} className="text-body-sm link-action">
            Browse auctions
          </Link>
          <h1 className="text-display text-foreground">{title}</h1>
          <p className="max-w-3xl text-body text-muted-foreground">
            {description}
          </p>
          <div className="surface-elevated max-w-3xl space-y-4 p-5 text-body-sm text-muted-foreground">
            {intro.split("\n\n").map((para) => (
              <p key={para.slice(0, 40)}>{para}</p>
            ))}
          </div>
          {topLinks && topLinks.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {topLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="min-h-[44px] rounded-full border border-border bg-muted px-4 py-2 text-sm font-medium text-action hover:bg-card"
                >
                  {link.label}
                </Link>
              ))}
            </div>
          )}
        </div>
        <AuctionDiscoveryView
          auctions={enriched}
          total={enriched.length}
          showHomeModules={false}
          showHero={false}
        />
        <SiteFooter />
      </main>
    </AppShell>
  );
}
