"use client";

import { useState } from "react";
import {
  Calendar,
  CalendarPlus,
  Clock,
  FileText,
  IndianRupee,
  MapPin,
  Star,
  User,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  Chip,
} from "@/components/ui/primitives";
import { LotDetails } from "@/components/lot-details";
import { LotPreviewStrip } from "@/components/lot-documents";
import { getClosingUrgency } from "@/lib/auction-filters";
import { commodityBorderClass } from "@/lib/commodity-styles";
import { listingPdfHref } from "@/lib/listing-pdf";
import {
  confidenceChipClass,
  emdStatusChipClass,
  formatChipLabel,
  lotTypeChipClass,
  priceStatusChipClass,
  regionChipClass,
} from "@/lib/chip-styles";
import {
  formatDateTime,
  formatInspection,
  formatInr,
  resolvePublicUrl,
  cn,
} from "@/lib/utils";
import { isLongSummary } from "@/lib/text-summary";
import {
  enrichAuctionDisplay,
  materialCategoryLabel,
  resolveDisplayBuyerSummary,
  resolveDisplayTitle,
} from "@/lib/display-enrichment";
import { countAuctionDocuments } from "@/lib/auction-documents";
import { resolveListingHero } from "@/lib/listing-media";
import { trackEvent } from "@/lib/analytics";
import { valuationBadgeLabel } from "@/lib/valuation";
import { deriveRouteId } from "@/lib/seo/route-id";
import { sourceToSlug } from "@/lib/seo/source-slug";
import type { AuctionRecord, AuctionSource } from "@/types/auction";

const SOURCE_LABELS: Record<AuctionSource, string> = {
  mstc: "MSTC",
  eauction: "eAuction",
  gem_forward: "GeM Forward",
};

function sourceBadgeLabel(source?: AuctionSource | null): string {
  const key = source ?? "mstc";
  return SOURCE_LABELS[key] ?? "MSTC";
}

function formatCategory(category?: string | null): string | null {
  if (!category) return null;
  return category.charAt(0).toUpperCase() + category.slice(1);
}

function PriceDisplay({ auction }: { auction: AuctionRecord }) {
  if (auction.price_summary) {
    return (
      <span className="text-xl font-bold tabular-nums text-foreground">
        {auction.price_summary}
      </span>
    );
  }
  const prices = auction.lots
    .map((l) => l.start_price_inr)
    .filter((p): p is number => p != null);
  if (prices.length === 0) {
    const fallback =
      auction.source === "mstc" ? "See PDF for price" : "See listing for price";
    return (
      <span className="text-sm font-medium text-muted-foreground">
        {fallback}
      </span>
    );
  }
  const unique = [...new Set(prices)].sort((a, b) => a - b);
  if (unique.length === 1) {
    return (
      <span className="text-xl font-bold tabular-nums text-foreground">
        {formatInr(unique[0])}
      </span>
    );
  }
  return (
    <span className="text-xl font-bold tabular-nums text-foreground">
      {formatInr(unique[0])} – {formatInr(unique[unique.length - 1])}
    </span>
  );
}

function hasInspection(auction: AuctionRecord): boolean {
  const text = formatInspection(
    auction.inspection_from,
    auction.inspection_to,
    auction.inspection,
  );
  return Boolean(text && text !== "—" && text !== "Not specified");
}

function ListingCardMedia({
  auction,
  href,
}: {
  auction: AuctionRecord;
  href: string;
}) {
  const hero = resolveListingHero(auction);
  const [broken, setBroken] = useState(false);
  return (
    <a
      href={href}
      className="relative block aspect-[20/19] overflow-hidden rounded-t-[var(--radius-xl)] bg-marketplace-gray-100 dark:bg-muted"
      aria-label="View listing photos"
    >
      {hero && !broken ? (
        <img
          src={hero.src}
          alt={hero.alt}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-hover ease-marketplace group-hover:scale-[1.02]"
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-gradient-to-br from-marketplace-gray-100 to-marketplace-gray-200 px-6 text-center dark:from-muted dark:to-card">
          <span className="text-footnote font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {sourceBadgeLabel(auction.source)}
          </span>
          <span className="line-clamp-2 text-body-sm font-semibold text-foreground">
            {resolveDisplayTitle(auction)}
          </span>
        </div>
      )}
    </a>
  );
}

function AuctionWarnings({ warnings }: { warnings?: string[] }) {
  if (!warnings?.length) return null;
  return (
    <p className="rounded-lg border border-border bg-muted px-3 py-2 text-xs text-muted-foreground">
      Data note: {warnings.join("; ")}
    </p>
  );
}

function formatListedDate(auction: AuctionRecord): string | null {
  if (auction.listed_at_label) return auction.listed_at_label;
  const iso =
    auction.listed_at ??
    (auction.listed_date ? `${auction.listed_date}T00:00:00+05:30` : null);
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const dt = new Date(t);
  const fmt = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const prefix =
    auction.listed_at_source === "opening_date_fallback"
      ? "Listed: approx. "
      : "Listed: ";
  return `${prefix}${fmt.format(dt)}`;
}

function formatImportedDate(auction: AuctionRecord): string | null {
  const iso = auction.imported_at ?? auction.first_seen_at;
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const fmt = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `Imported: ${fmt.format(new Date(t))}`;
}

function gemDocumentLabel(url: string, index: number, total: number): string {
  const lower = url.toLowerCase();
  if (lower.includes("rule"))
    return total > 1 ? `GeM rules ${index + 1}` : "GeM rules";
  if (lower.includes("notice") || lower.includes("brief")) {
    return total > 1 ? `GeM notice ${index + 1}` : "GeM notice";
  }
  return total > 1 ? `GeM document ${index + 1}` : "GeM document";
}

export function AuctionCard({
  auction: rawAuction,
  index,
  watched = false,
  onToggleWatch,
  compact: _compact = false,
  onOpenDiligence,
  onToggleCompare: _onToggleCompare,
  inCompare: _inCompare = false,
  searchQuery: _searchQuery,
}: {
  auction: AuctionRecord;
  index: number;
  watched?: boolean;
  onToggleWatch?: (id: string) => void;
  compact?: boolean;
  onOpenDiligence?: () => void;
  onToggleCompare?: () => void;
  inCompare?: boolean;
  searchQuery?: string;
}) {
  const auction = enrichAuctionDisplay(rawAuction);
  const [showFullNotice, setShowFullNotice] = useState(false);
  const cardTitle = resolveDisplayTitle(rawAuction);
  const buyerSummary = resolveDisplayBuyerSummary(rawAuction);
  const fullSummary = auction.item_summary || cardTitle;
  const longNotice =
    fullSummary !== cardTitle &&
    (isLongSummary(fullSummary, 80) || fullSummary.length > cardTitle.length + 20);
  const cityState =
    auction.display_location_city && auction.display_location_state
      ? `${auction.display_location_city}, ${auction.display_location_state}`
      : (auction.display_location_city ??
        auction.display_location_state ??
        null);
  const rawSite =
    auction.display_location_raw &&
    cityState &&
    auction.display_location_raw.toLowerCase() !== cityState.toLowerCase()
      ? auction.display_location_raw
      : auction.display_location_raw && !cityState
        ? auction.display_location_raw
        : null;
  const materialLabel = materialCategoryLabel(
    auction.display_material_category,
  );
  const pdfHref = listingPdfHref(auction);
  const localDetailHref = resolvePublicUrl(
    `${sourceToSlug(auction.source)}/${deriveRouteId(auction)}/`,
  );
  const urgency = getClosingUrgency(auction.closing);
  const categoryLabel = formatCategory(auction.asset_category);
  const valuationLabel = valuationBadgeLabel(auction);
  const docCounts = countAuctionDocuments(auction);
  const lowLocationConfidence = auction.display_location_confidence === "low";

  return (
    <Card className={cn("group relative overflow-hidden", commodityBorderClass(auction))}>
      <ListingCardMedia auction={auction} href={localDetailHref} />
      <CardHeader className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex items-start gap-2">
              {onToggleWatch && (
                <button
                  type="button"
                  onClick={() => {
                    onToggleWatch(auction.id);
                    trackEvent("watchlist_toggle", {
                      auction_id: auction.id,
                      watched: !watched,
                    });
                  }}
                  className="inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-full border border-border bg-card text-action shadow-sm hover:border-action"
                  aria-label={
                    watched ? "Remove from watchlist" : "Save to watchlist"
                  }
                >
                  <Star
                    className={`h-4 w-4 ${watched ? "fill-action text-action" : ""}`}
                  />
                </button>
              )}
              <a
                href={localDetailHref}
                className="text-title text-foreground transition-colors hover:text-action line-clamp-2"
              >
                {cardTitle}
              </a>
            </div>
            {longNotice && (
              <div className="space-y-1 pl-0 sm:pl-12">
                <p
                  className={cn(
                    "text-body-sm text-muted-foreground",
                    !showFullNotice && "line-clamp-3",
                  )}
                >
                  {fullSummary}
                </p>
                <button
                  type="button"
                  onClick={() => setShowFullNotice((v) => !v)}
                  className="text-footnote font-medium link-action hover:underline"
                >
                  {showFullNotice
                    ? "Hide full notice text"
                    : "Show full notice text"}
                </button>
              </div>
            )}
            {auction.display_quantity_summary && (
              <p className="text-body-sm font-medium text-muted-foreground">
                {auction.display_quantity_summary}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-1.5">
              <Chip className="border-border bg-muted text-foreground">
                {sourceBadgeLabel(auction.source)}
              </Chip>
              {urgency && (
                <Chip className={urgency.chipClass}>{urgency.label}</Chip>
              )}
              <Chip className={regionChipClass()}>{auction.region}</Chip>
              {categoryLabel && (
                <Chip className="border-border bg-muted/60 text-muted-foreground">
                  {categoryLabel}
                </Chip>
              )}
              {materialLabel && (
                <Chip className="border-border bg-muted/60 text-muted-foreground">
                  {materialLabel}
                </Chip>
              )}
              {auction.lot_types?.slice(0, 2).map((t) => (
                <Chip
                  key={t}
                  className={cn(lotTypeChipClass(), "text-muted-foreground")}
                >
                  {t}
                </Chip>
              ))}
              {auction.parse_confidence &&
                auction.parse_confidence !== "high" && (
                  <Chip
                    className={confidenceChipClass(auction.parse_confidence)}
                  >
                    {auction.parse_confidence}
                  </Chip>
                )}
              {auction.price_parse_status &&
                auction.price_parse_status !== "numeric" &&
                auction.price_parse_status !== "range" && (
                  <Chip
                    className={priceStatusChipClass(
                      auction.price_parse_status,
                    )}
                  >
                    {formatChipLabel(auction.price_parse_status)}
                  </Chip>
                )}
              {auction.emd_parse_status && (
                <Chip className={emdStatusChipClass(auction.emd_parse_status)}>
                  EMD {formatChipLabel(auction.emd_parse_status)}
                </Chip>
              )}
              {valuationLabel && (
                <Chip className="border-border bg-muted/60 text-muted-foreground">
                  {valuationLabel}
                </Chip>
              )}
            </div>
            {buyerSummary && (
              <p className="text-footnote text-muted-foreground">
                {buyerSummary}
              </p>
            )}
            {auction.display_key_lots &&
              auction.display_key_lots.length > 1 && (
                <p className="text-footnote text-muted-foreground">
                  {auction.display_key_lots.join(" · ")}
                </p>
              )}
          </div>
          <div className="shrink-0 rounded-[var(--radius-lg)] border border-[color-mix(in_srgb,var(--color-rausch)_22%,white)] bg-[color-mix(in_srgb,var(--color-rausch)_6%,white)] px-[var(--space-20)] py-[var(--space-12)] text-right dark:border-border dark:bg-muted">
            <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
              Price
            </p>
            <PriceDisplay auction={auction} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-2 sm:grid-cols-2">
          {cityState && (
            <div className="flex items-start gap-2 sm:col-span-2">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" />
              <span className="font-medium text-foreground">
                {cityState}
                {lowLocationConfidence && (
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    (location uncertain)
                  </span>
                )}
              </span>
            </div>
          )}
          {rawSite && (
            <div className="flex items-start gap-2 sm:col-span-2">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="text-muted-foreground">Site: {rawSite}</span>
            </div>
          )}
          {!cityState && !rawSite && (auction.location || auction.state) && (
            <div className="flex items-start gap-2 sm:col-span-2">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" />
              <span className="text-muted-foreground">
                {auction.location || auction.state}
              </span>
            </div>
          )}
          {auction.seller && (
            <div className="flex items-start gap-2">
              <User className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" />
              <span className="text-muted-foreground">{auction.seller}</span>
            </div>
          )}
          <div className="flex items-start gap-2">
            <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" />
            <span className="text-muted-foreground">
              Opens {formatDateTime(auction.opening)}
            </span>
          </div>
          <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[#ffd1dc] bg-[#fff8fa] px-3 py-2 dark:border-border dark:bg-muted">
            <Clock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="font-medium tabular-nums text-foreground">
              Closes {formatDateTime(auction.closing)}
            </span>
          </div>
          {formatListedDate(auction) && (
            <div className="flex items-start gap-2 sm:col-span-2">
              <CalendarPlus className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="text-muted-foreground">
                {formatListedDate(auction)}
              </span>
            </div>
          )}
          {formatImportedDate(auction) && (
            <div className="flex items-start gap-2 sm:col-span-2">
              <CalendarPlus className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" />
              <span className="text-footnote text-muted-foreground">
                {formatImportedDate(auction)}
              </span>
            </div>
          )}
          {hasInspection(auction) && (
            <div className="flex items-start gap-2 sm:col-span-2">
              <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/70" />
              <span className="text-muted-foreground">
                Inspection:{" "}
                {formatInspection(
                  auction.inspection_from,
                  auction.inspection_to,
                  auction.inspection,
                )}
              </span>
            </div>
          )}
          {auction.emd_summary && (
            <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-border bg-muted/50 px-3 py-2 sm:col-span-2">
              <IndianRupee className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="font-medium text-foreground">
                {auction.emd_summary}
              </span>
            </div>
          )}
          {auction.tax_summary && (
            <div className="text-muted-foreground sm:col-span-2">
              Taxes: {auction.tax_summary}
            </div>
          )}
          {(docCounts.documents > 0 || docCounts.photos > 0) && (
            <div className="flex items-center gap-2 sm:col-span-2">
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">
                {docCounts.documents > 0 &&
                  `${docCounts.documents} doc${docCounts.documents === 1 ? "" : "s"}`}
                {docCounts.documents > 0 && docCounts.photos > 0 && " · "}
                {docCounts.photos > 0 &&
                  `${docCounts.photos} photo${docCounts.photos === 1 ? "" : "s"}`}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <a href={localDetailHref} className="btn-secondary">
            View details
          </a>

          {pdfHref && (
            <a
              href={pdfHref}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
              onClick={() => trackEvent("pdf_open", { auction_id: auction.id })}
            >
              <FileText className="h-4 w-4" />
              Open PDF
            </a>
          )}
        </div>

        {auction.document_urls && auction.document_urls.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {auction.document_urls.map((url, i) => (
              <a
                key={`${url}-${i}`}
                href={url.startsWith("http") ? url : resolvePublicUrl(url)}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary inline-flex items-center gap-2 text-xs"
              >
                <FileText className="h-3.5 w-3.5" />
                {auction.source === "gem_forward"
                  ? gemDocumentLabel(url, i, auction.document_urls!.length)
                  : `Document ${auction.document_urls!.length > 1 ? i + 1 : ""}`.trim()}
              </a>
            ))}
          </div>
        )}

        <LotPreviewStrip lots={auction.lots} max={3} />

        <AuctionWarnings warnings={auction.warnings} />
        <LotDetails lots={auction.lots} />
      </CardContent>
    </Card>
  );
}
