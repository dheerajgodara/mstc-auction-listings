"use client";

import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { AuctionDetailAnalytics } from "@/components/auction-detail-analytics";
import { AuctionDetailLots } from "@/components/auction-detail-lots";
import { SiteDisclaimer } from "@/components/site-disclaimer";
import { ExpandableText } from "@/components/expandable-text";
import { resolveNoticeBody } from "@/lib/text-summary";
import { countAuctionDocuments } from "@/lib/auction-documents";
import { listingPdfHref } from "@/lib/listing-pdf";
import {
  aiTagLabel,
  enrichAuctionDisplay,
  isAiReady,
  resolveAiTags,
  resolveDisplayBuyerSummary,
  resolveDisplayTitle,
} from "@/lib/display-enrichment";
import {
  buildAuctionBreadcrumbJsonLd,
  buildAuctionEventJsonLd,
  buildAuctionLotsItemListJsonLd,
  buildAuctionWebPageJsonLd,
  buildPublisherOrganizationJsonLd,
  officialPortalLabel,
} from "@/lib/seo/json-ld";
import { isActiveOrUpcomingClosing } from "@/lib/seo/index-policy";
import { sourceLabel } from "@/lib/discovery-constants";
import { SITE_BASE_URL } from "@/lib/site-url";
import { formatDateTime, resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";

function JsonLd({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return null;
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}

export function AuctionDetailPageApp({
  auction: raw,
}: {
  auction: AuctionRecord;
}) {
  const auction = enrichAuctionDisplay(raw);
  const active = isActiveOrUpcomingClosing(auction.closing);
  const title = resolveDisplayTitle(raw);
  const aiSummary = resolveDisplayBuyerSummary(raw);
  const aiTags = resolveAiTags(raw);
  const showAiSummary =
    isAiReady(raw) && aiSummary && aiSummary !== auction.display_buyer_summary;
  const cityState =
    auction.display_location_city && auction.display_location_state
      ? `${auction.display_location_city}, ${auction.display_location_state}`
      : (auction.display_location_city ??
        auction.display_location_state ??
        null);
  const docCounts = countAuctionDocuments(auction);
  const pdfHref = listingPdfHref(auction);
  const source = sourceLabel(auction.source);
  const portal = officialPortalLabel(auction.source);
  const locationAnswer =
    cityState ??
    auction.display_location_raw ??
    auction.location ??
    "Location not stated in the public listing — confirm on the official portal.";
  const quantityAnswer =
    auction.display_quantity_summary ??
    (auction.display_total_quantity_mt != null
      ? `About ${auction.display_total_quantity_mt} MT (estimated from listing data).`
      : "Quantity is not summarized here — check lot lines and the official catalogue.");
  const priceAnswer = [
    auction.price_summary ? `Price: ${auction.price_summary}.` : null,
    auction.emd_summary ? `EMD: ${auction.emd_summary}.` : null,
    auction.tax_summary ? `Tax notes: ${auction.tax_summary}.` : null,
  ]
    .filter(Boolean)
    .join(" ");
  const docsAnswer =
    docCounts.documents > 0 || docCounts.photos > 0
      ? `This page lists ${docCounts.documents} cached document(s) and ${docCounts.photos} photo(s) when available locally. Always verify the full set on ${portal}.`
      : `No locally cached documents or photos are attached on this page. Check the official ${portal} listing for catalogues and images.`;

  return (
    <AppShell>
      <AuctionDetailAnalytics
        auctionId={auction.id}
        source={auction.source ?? "mstc"}
      />
      <JsonLd data={buildAuctionEventJsonLd(auction)} />
      <JsonLd data={buildAuctionBreadcrumbJsonLd(auction)} />
      <JsonLd data={buildAuctionWebPageJsonLd(auction)} />
      <JsonLd data={buildAuctionLotsItemListJsonLd(auction)} />
      <JsonLd data={buildPublisherOrganizationJsonLd()} />

      <nav
        aria-label="Auction sections"
        className="sticky top-[var(--nav-height-regular)] z-sticky border-b border-border bg-card/95 backdrop-blur-sm"
      >
        <div className="container-marketplace flex gap-4 overflow-x-auto py-2 text-sm">
          <a href="#overview" className="shrink-0 link-action">
            Overview
          </a>
          <a href="#lots" className="shrink-0 text-muted-foreground hover:text-foreground">
            Lots
          </a>
          {pdfHref && (
            <a href={pdfHref} className="ml-auto shrink-0 font-medium link-action">
              View listing PDF
            </a>
          )}
        </div>
      </nav>

      <main
        id="overview"
        className="container-marketplace space-y-6 py-8"
      >
        <nav aria-label="Breadcrumb" className="text-body-sm text-muted-foreground">
          <ol className="flex flex-wrap items-center gap-2">
            <li>
              <Link href={SITE_BASE_URL} className="link-action">
                Browse auctions
              </Link>
            </li>
            <li aria-hidden className="text-marketplace-gray-500">
              /
            </li>
            <li>{source}</li>
            <li aria-hidden className="text-marketplace-gray-500">
              /
            </li>
            <li className="font-medium text-foreground">
              {auction.auction_number}
            </li>
          </ol>
        </nav>

        {!active && (
          <p className="rounded-lg border border-border bg-muted px-4 py-3 text-body-sm font-medium text-foreground">
            This auction has closed. Details are shown for reference — verify
            current listings on the official source before bidding.
          </p>
        )}

        <header className="space-y-4">
          <p className="text-body-sm font-medium link-action">{source}</p>
          <h1 className="text-display text-foreground">{title}</h1>
          {auction.display_quantity_summary && (
            <p className="text-headline text-lg text-foreground">
              {auction.display_quantity_summary}
            </p>
          )}
          {auction.display_buyer_summary && (
            <p className="max-w-3xl text-body text-muted-foreground">
              {auction.display_buyer_summary}
            </p>
          )}
          {showAiSummary && (
            <div className="max-w-3xl space-y-2">
              <p className="text-caption text-muted-foreground">
                AI-assisted summary
              </p>
              <p className="text-body text-muted-foreground">{aiSummary}</p>
            </div>
          )}
          {aiTags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {aiTags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-border bg-muted/50 px-2.5 py-0.5 text-caption text-muted-foreground"
                >
                  {aiTagLabel(tag)}
                </span>
              ))}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {cityState && (
              <div className="surface-elevated p-3">
                <p className="text-caption">Location</p>
                <p className="font-medium text-foreground">{cityState}</p>
                {auction.display_location_raw && (
                  <p className="mt-0.5 text-body-sm text-muted-foreground">
                    {auction.display_location_raw}
                  </p>
                )}
              </div>
            )}
            <div className="surface-elevated p-3">
              <p className="text-caption">Closes</p>
              <p className="font-medium tabular-nums text-foreground">
                {formatDateTime(auction.closing)}
              </p>
            </div>
            {auction.emd_summary && (
              <div className="surface-elevated p-3">
                <p className="text-caption">EMD</p>
                <p className="font-medium tabular-nums text-foreground">
                  {auction.emd_summary}
                </p>
              </div>
            )}
            {auction.price_summary && (
              <div className="surface-elevated p-3">
                <p className="text-caption">Price</p>
                <p className="font-semibold tabular-nums text-action">
                  {auction.price_summary}
                </p>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {pdfHref && (
              <a
                href={pdfHref}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary"
              >
                View listing PDF
              </a>
            )}
          </div>

          {(docCounts.documents > 0 || docCounts.photos > 0) && (
            <section aria-label="Evidence assets" className="space-y-2">
              <p className="text-caption">
                Evidence · {docCounts.documents} docs · {docCounts.photos}{" "}
                photos
              </p>
            </section>
          )}
        </header>

        {(() => {
          const notice = resolveNoticeBody({
            item_summary: auction.item_summary,
            display_title: title,
            lots: auction.lots,
          });
          if (!notice) return null;
          return (
            <section
              aria-labelledby="auction-notice-heading"
              className="surface-elevated space-y-3 p-4"
            >
              <h2
                id="auction-notice-heading"
                className="text-heading text-foreground"
              >
                What’s being sold
              </h2>
              <ExpandableText text={notice} previewLen={700} />
            </section>
          );
        })()}

        <section
          aria-labelledby="auction-details-heading"
          className="surface-elevated space-y-4 p-4"
        >
          <h2 id="auction-details-heading" className="text-heading text-foreground">
            Auction details
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-caption">Auction number</p>
              <p className="font-medium tabular-nums">{auction.auction_number}</p>
            </div>
            <div>
              <p className="text-caption">Opens</p>
              <p className="font-medium tabular-nums">
                {formatDateTime(auction.opening)}
              </p>
            </div>
            {(auction.imported_at || auction.first_seen_at) && (
              <div>
                <p className="text-caption">Imported</p>
                <p className="font-medium tabular-nums">
                  {formatDateTime(
                    auction.imported_at ?? auction.first_seen_at,
                  )}
                </p>
              </div>
            )}
            {auction.seller && (
              <div className="sm:col-span-2">
                <p className="text-caption">Seller / department</p>
                <p className="font-medium">{auction.seller}</p>
              </div>
            )}
            {auction.tax_summary && (
              <div className="sm:col-span-2">
                <p className="text-caption">Taxes</p>
                <p className="tabular-nums">{auction.tax_summary}</p>
              </div>
            )}
            <div>
              <p className="text-caption">Lots</p>
              <p className="font-medium tabular-nums">{auction.lots.length}</p>
            </div>
          </div>
        </section>

        <section
          aria-labelledby="auction-answers-heading"
          className="surface-elevated space-y-4 p-4"
        >
          <h2 id="auction-answers-heading" className="text-heading text-foreground">
            Quick answers
          </h2>
          <dl className="space-y-4 text-body text-muted-foreground">
            <div data-machine-faq="what" id="faq-what">
              <dt className="font-medium text-foreground">
                What is being auctioned?
              </dt>
              <dd className="mt-1">
                {title}
                {(() => {
                  const notice = resolveNoticeBody({
                    item_summary: auction.item_summary,
                    display_title: title,
                    lots: auction.lots,
                  });
                  if (!notice || notice === title) return "";
                  return ` ${notice}`;
                })()}
                {auction.lots.length > 0
                  ? ` This listing includes ${auction.lots.length} lot${auction.lots.length === 1 ? "" : "s"}.`
                  : ""}
              </dd>
            </div>
            <div data-machine-faq="where" id="faq-where">
              <dt className="font-medium text-foreground">Where is it located?</dt>
              <dd className="mt-1">{locationAnswer}</dd>
            </div>
            <div data-machine-faq="quantity" id="faq-quantity">
              <dt className="font-medium text-foreground">How much quantity?</dt>
              <dd className="mt-1">{quantityAnswer}</dd>
            </div>
            <div data-machine-faq="closing" id="faq-closing">
              <dt className="font-medium text-foreground">
                What is the closing date?
              </dt>
              <dd className="mt-1 tabular-nums">
                {formatDateTime(auction.closing)}
                {auction.opening
                  ? ` Opens ${formatDateTime(auction.opening)}.`
                  : ""}{" "}
                Confirm live closing (including anti-sniping extensions) on{" "}
                {portal}.
              </dd>
            </div>
            <div data-machine-faq="price" id="faq-price">
              <dt className="font-medium text-foreground">
                What are price / EMD / GST / TCS?
              </dt>
              <dd className="mt-1">
                {priceAnswer ||
                  "Price, EMD, and tax details are not fully summarized here — verify floor price, EMD, GST, and TCS on the official portal."}
              </dd>
            </div>
            <div data-machine-faq="documents" id="faq-documents">
              <dt className="font-medium text-foreground">
                What documents/photos are available?
              </dt>
              <dd className="mt-1">{docsAnswer}</dd>
            </div>
            <div data-machine-faq="bid" id="faq-bid">
              <dt className="font-medium text-foreground">
                Where to bid officially?
              </dt>
              <dd className="mt-1">
                Bid only on the official {portal} portal. Scrap Auction India is
                a discovery site and does not accept bids or payments.
              </dd>
            </div>
          </dl>
        </section>

        <div id="lots">
          <AuctionDetailLots lots={auction.lots} />
        </div>
        <SiteDisclaimer />
      </main>

      <SiteFooter />
    </AppShell>
  );
}
