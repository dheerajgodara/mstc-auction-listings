"use client";

import { useState } from "react";
import {
  Calendar,
  CalendarPlus,
  Clock,
  ExternalLink,
  FileText,
  IndianRupee,
  MapPin,
  Star,
  User,
} from "lucide-react";
import { Card, CardContent, CardHeader, Chip } from "@/components/ui/primitives";
import { FadeIn } from "@/components/magic/fade-in";
import { LotDetails } from "@/components/lot-details";
import { LotPreviewStrip } from "@/components/lot-documents";
import { getClosingUrgency } from "@/lib/auction-filters";
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
} from "@/lib/utils";
import { isLongSummary } from "@/lib/text-summary";
import {
  enrichAuctionDisplay,
  materialCategoryLabel,
} from "@/lib/display-enrichment";
import { valuationBadgeLabel } from "@/lib/valuation";
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
      <span className="text-xl font-bold text-cyan-900">{auction.price_summary}</span>
    );
  }
  const prices = auction.lots
    .map((l) => l.start_price_inr)
    .filter((p): p is number => p != null);
  if (prices.length === 0) {
    const fallback =
      auction.source === "mstc" ? "See PDF for price" : "See listing for price";
    return <span className="text-sm font-medium text-slate-500">{fallback}</span>;
  }
  const unique = [...new Set(prices)].sort((a, b) => a - b);
  if (unique.length === 1) {
    return <span className="text-xl font-bold text-cyan-900">{formatInr(unique[0])}</span>;
  }
  return (
    <span className="text-xl font-bold text-cyan-900">
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

function detailLinkLabel(source?: AuctionSource | null): string {
  if (source === "eauction") return "Open details";
  return `View on ${sourceBadgeLabel(source)}`;
}

function AuctionWarnings({ warnings }: { warnings?: string[] }) {
  if (!warnings?.length) return null;
  return (
    <p className="rounded-lg border border-amber-200/70 bg-amber-50/80 px-3 py-2 text-xs text-amber-900">
      Data note: {warnings.join("; ")}
    </p>
  );
}

function formatListedDate(auction: AuctionRecord): string | null {
  if (auction.listed_at_label) return auction.listed_at_label;
  const iso = auction.listed_at ?? (auction.listed_date ? `${auction.listed_date}T00:00:00+05:30` : null);
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
    auction.listed_at_source === "opening_date_fallback" ? "Listed: approx. " : "Listed: ";
  return `${prefix}${fmt.format(dt)}`;
}

function gemDocumentLabel(url: string, index: number, total: number): string {
  const lower = url.toLowerCase();
  if (lower.includes("rule")) return total > 1 ? `GeM rules ${index + 1}` : "GeM rules";
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
}: {
  auction: AuctionRecord;
  index: number;
  watched?: boolean;
  onToggleWatch?: (id: string) => void;
}) {
  const auction = enrichAuctionDisplay(rawAuction);
  const [showFullNotice, setShowFullNotice] = useState(false);
  const cardTitle = auction.display_title || auction.item_summary || "—";
  const fullSummary = auction.item_summary || cardTitle;
  const longNotice = isLongSummary(fullSummary) && fullSummary !== cardTitle;
  const cardSummary = showFullNotice ? fullSummary : cardTitle;
  const cityState =
    auction.display_location_city && auction.display_location_state
      ? `${auction.display_location_city}, ${auction.display_location_state}`
      : auction.display_location_city ?? auction.display_location_state ?? null;
  const rawSite =
    auction.display_location_raw &&
    cityState &&
    auction.display_location_raw.toLowerCase() !== cityState.toLowerCase()
      ? auction.display_location_raw
      : auction.display_location_raw && !cityState
        ? auction.display_location_raw
        : null;
  const materialLabel = materialCategoryLabel(auction.display_material_category);
  const pdfHref = resolvePublicUrl(auction.pdf_url);
  const detailHref = auction.detail_url?.startsWith("http")
    ? auction.detail_url
    : resolvePublicUrl(auction.detail_url ?? undefined);
  const urgency = getClosingUrgency(auction.closing);
  const categoryLabel = formatCategory(auction.asset_category);
  const valuationLabel = valuationBadgeLabel(auction);

  return (
    <FadeIn delay={Math.min(index * 0.02, 0.25)}>
      <Card className="relative">
        <div
          className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-cyan-400 via-sky-400 to-violet-400"
          aria-hidden
        />
        <CardHeader className="space-y-3 pl-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {onToggleWatch && (
                  <button
                    type="button"
                    onClick={() => onToggleWatch(auction.id)}
                    className="rounded-full border border-amber-200/80 bg-amber-50/90 p-1 text-amber-700 hover:bg-amber-100"
                    aria-label={watched ? "Remove from watchlist" : "Save to watchlist"}
                  >
                    <Star className={`h-3.5 w-3.5 ${watched ? "fill-amber-500" : ""}`} />
                  </button>
                )}
                <Chip className="border-slate-200/80 bg-slate-50/90 text-slate-800">
                  {sourceBadgeLabel(auction.source)}
                </Chip>
                {categoryLabel && (
                  <Chip className="border-emerald-200/80 bg-emerald-50/90 text-emerald-900">
                    {categoryLabel}
                  </Chip>
                )}
                {materialLabel && (
                  <Chip className="border-sky-200/80 bg-sky-50/90 text-sky-900">
                    {materialLabel}
                  </Chip>
                )}
                <Chip className={regionChipClass()}>{auction.region}</Chip>
                {auction.lot_types?.map((t) => (
                  <Chip key={t} className={lotTypeChipClass()}>
                    {t}
                  </Chip>
                ))}
                {auction.parse_confidence && (
                  <Chip className={confidenceChipClass(auction.parse_confidence)}>
                    {auction.parse_confidence}
                  </Chip>
                )}
                {auction.price_parse_status && (
                  <Chip className={priceStatusChipClass(auction.price_parse_status)}>
                    {formatChipLabel(auction.price_parse_status)}
                  </Chip>
                )}
                {auction.emd_parse_status && (
                  <Chip className={emdStatusChipClass(auction.emd_parse_status)}>
                    EMD {formatChipLabel(auction.emd_parse_status)}
                  </Chip>
                )}
                {urgency && (
                  <Chip className={urgency.chipClass}>{urgency.label}</Chip>
                )}
                {valuationLabel && (
                  <Chip className="border-violet-200/80 bg-violet-50/90 text-violet-900">
                    {valuationLabel}
                  </Chip>
                )}
              </div>
              <h2
                className={`text-lg font-semibold leading-snug text-slate-900 ${
                  showFullNotice ? "" : "line-clamp-2"
                }`}
              >
                {cardSummary}
              </h2>
              {auction.display_quantity_summary && (
                <p className="text-sm font-medium text-slate-700">
                  {auction.display_quantity_summary}
                </p>
              )}
              {auction.display_key_lots && auction.display_key_lots.length > 1 && (
                <p className="text-xs text-slate-600">
                  {auction.display_key_lots.join(" · ")}
                </p>
              )}
              {longNotice && (
                <button
                  type="button"
                  onClick={() => setShowFullNotice((v) => !v)}
                  className="text-xs font-medium text-cyan-800 hover:underline"
                >
                  {showFullNotice ? "Hide full notice text" : "Show full notice text"}
                </button>
              )}
            </div>
            <div className="shrink-0 rounded-xl border border-cyan-200/60 bg-gradient-to-br from-cyan-50/90 to-sky-50/90 px-4 py-2 text-right">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-700/80">
                Price
              </p>
              <PriceDisplay auction={auction} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 pl-5 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            {cityState && (
              <div className="flex items-start gap-2 sm:col-span-2">
                <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600/70" />
                <span className="font-medium text-slate-800">{cityState}</span>
              </div>
            )}
            {rawSite && (
              <div className="flex items-start gap-2 sm:col-span-2">
                <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                <span className="text-slate-600">Site: {rawSite}</span>
              </div>
            )}
            {!cityState && !rawSite && (auction.location || auction.state) && (
              <div className="flex items-start gap-2 sm:col-span-2">
                <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600/70" />
                <span className="text-slate-700">
                  {auction.location || auction.state}
                </span>
              </div>
            )}
            {auction.seller && (
              <div className="flex items-start gap-2">
                <User className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600/70" />
                <span className="text-slate-700">{auction.seller}</span>
              </div>
            )}
            <div className="flex items-start gap-2">
              <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600/70" />
              <span className="text-slate-700">Opens {formatDateTime(auction.opening)}</span>
            </div>
            <div className="flex items-start gap-2 rounded-lg border border-amber-200/50 bg-amber-50/50 px-2 py-1.5">
              <Clock className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span className="font-medium text-amber-950">
                Closes {formatDateTime(auction.closing)}
              </span>
            </div>
            {formatListedDate(auction) && (
              <div className="flex items-start gap-2 sm:col-span-2">
                <CalendarPlus className="mt-0.5 h-4 w-4 shrink-0 text-violet-600/80" />
                <span className="text-slate-700">{formatListedDate(auction)}</span>
              </div>
            )}
            {hasInspection(auction) && (
              <div className="flex items-start gap-2 sm:col-span-2">
                <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600/70" />
                <span className="text-slate-700">
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
              <div className="flex items-start gap-2 rounded-lg border border-emerald-200/50 bg-emerald-50/50 px-2 py-1.5 sm:col-span-2">
                <IndianRupee className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                <span className="font-medium text-emerald-950">{auction.emd_summary}</span>
              </div>
            )}
            {auction.tax_summary && (
              <div className="text-slate-600 sm:col-span-2">
                Taxes: {auction.tax_summary}
              </div>
            )}
          </div>

          {pdfHref && (
            <a
              href={pdfHref}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-glass-primary"
            >
              <FileText className="h-4 w-4" />
              Open PDF
            </a>
          )}

          {detailHref && detailHref !== pdfHref && (
            <a
              href={detailHref}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-glass inline-flex items-center gap-2"
            >
              <ExternalLink className="h-4 w-4" />
              {detailLinkLabel(auction.source)}
            </a>
          )}

          {auction.document_urls && auction.document_urls.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {auction.document_urls.map((url, i) => (
                <a
                  key={`${url}-${i}`}
                  href={url.startsWith("http") ? url : resolvePublicUrl(url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-glass inline-flex items-center gap-2 text-xs"
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
    </FadeIn>
  );
}
