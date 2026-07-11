"use client";

import { SiteDisclaimer } from "@/components/site-disclaimer";
import { AccordionItem } from "@/components/ui/accordion";
import { resolvePublicUrl } from "@/lib/utils";

const FOOTER_SECTIONS = [
  {
    title: "Sources",
    links: [
      { href: "mstc-auctions/", label: "MSTC auctions" },
      { href: "gem-forward-auctions/", label: "GeM Forward" },
      { href: "eauction-gov-in/", label: "eAuction.gov.in" },
      { href: "scrap/", label: "Scrap auctions" },
    ],
  },
  {
    title: "Materials",
    links: [
      { href: "hub/material/ferrous_scrap/", label: "Material hubs" },
      { href: "metal-scrap/", label: "Metal scrap" },
      { href: "vehicle-auctions/", label: "Vehicles" },
      { href: "coal-auctions/", label: "Coal" },
    ],
  },
  {
    title: "Tools",
    links: [
      { href: "watchlist/", label: "Watchlist" },
      { href: "map/", label: "Map" },
      { href: "insights/", label: "Insights" },
      { href: "saved/", label: "Saved searches" },
      { href: "app/", label: "Install app" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "pricing/", label: "Pricing" },
      { href: "terms/", label: "Terms" },
      { href: "privacy/", label: "Privacy" },
      { href: "support/", label: "Support" },
      { href: "status/", label: "Import & data status" },
      { href: "accessibility/", label: "Accessibility" },
    ],
  },
  {
    title: "Company",
    links: [
      { href: "", label: "Discover auctions" },
      { href: "hub/region/ncr/", label: "Regions" },
      { href: "accessibility/", label: "Accessibility" },
    ],
  },
] as const;

export function SiteFooter({ automationRanAt }: { automationRanAt?: string }) {
  return (
    <footer className="mt-16 border-t border-border bg-marketplace-gray-100 dark:bg-card">
      <div className="container-marketplace py-10">
        <div className="hidden gap-8 lg:grid lg:grid-cols-5">
          {FOOTER_SECTIONS.map((section) => (
            <div key={section.title}>
              <h2 className="mb-3 text-xs font-semibold text-foreground">
                {section.title}
              </h2>
              <ul className="space-y-2">
                {section.links.map((link) => (
                  <li key={link.href}>
                    <a
                      href={resolvePublicUrl(link.href)}
                      className="text-footnote link-action"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="lg:hidden">
          {FOOTER_SECTIONS.map((section) => (
            <AccordionItem key={section.title} title={section.title}>
              <ul className="space-y-2">
                {section.links.map((link) => (
                  <li key={link.href}>
                    <a
                      href={resolvePublicUrl(link.href)}
                      className="link-action"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </AccordionItem>
          ))}
        </div>
        <div className="mt-8 space-y-3 border-t border-border pt-6">
          <SiteDisclaimer />
          <p className="text-footnote text-muted-foreground">
            Data sources: MSTC, GeM Forward, eAuction.gov.in.
            {automationRanAt ? ` Pipeline ran: ${automationRanAt}.` : ""}
          </p>
          <p className="text-footnote text-muted-foreground">
            © Scrap Auction India. Bidding and payments occur only on official
            source portals.
          </p>
        </div>
      </div>
    </footer>
  );
}
