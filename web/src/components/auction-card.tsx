"use client";

import {
  Calendar,
  Clock,
  ExternalLink,
  FileText,
  IndianRupee,
  MapPin,
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

export function AuctionCard({
  auction,
  index,
}: {
  auction: AuctionRecord;
  index: number;
}) {
  const itemDetails = auction.item_summary || "—";
  const displayLocation =
    auction.location || auction.lots[0]?.location || auction.state || "—";
  const pdfHref = resolvePublicUrl(auction.pdf_url);
  const detailHref = auction.detail_url?.startsWith("http")
    ? auction.detail_url
    : resolvePublicUrl(auction.detail_url ?? undefined);
  const urgency = getClosingUrgency(auction.closing);
  const categoryLabel = formatCategory(auction.asset_category);

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
                <Chip className="border-slate-200/80 bg-slate-50/90 text-slate-800">
                  {sourceBadgeLabel(auction.source)}
                </Chip>
                {categoryLabel && (
                  <Chip className="border-emerald-200/80 bg-emerald-50/90 text-emerald-900">
                    {categoryLabel}
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
              </div>
              <h2 className="text-lg font-semibold leading-snug text-slate-900">
                {itemDetails}
              </h2>
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
            <div className="flex items-start gap-2">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-cyan-600/70" />
              <span className="text-slate-700">{displayLocation}</span>
            </div>
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
                  Document {auction.document_urls!.length > 1 ? i + 1 : ""}
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
