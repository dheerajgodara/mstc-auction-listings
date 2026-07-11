"use client";
import { useEffect, useMemo, useState } from "react";
import {
  CalendarPlus,
  ChevronRight,
  Copy,
  ExternalLink,
  IndianRupee,
  MessageCircle,
  Printer,
  X,
} from "lucide-react";
import {
  InspectionReport,
  extractLiftingWindow,
  extractPlantAccessRules,
} from "@/components/inspection-report";
import { useUpgradePrompt } from "@/components/upgrade-prompt";
import {
  LandedCostEstimator,
  parseGstPercent,
} from "@/components/landed-cost-estimator";
import { LotDetails } from "@/components/lot-details";
import { LotPreviewStrip } from "@/components/lot-documents";
import { PostAuctionTracker } from "@/components/post-auction-tracker";
import { ReportIssueForm } from "@/components/report-issue-form";
import { canUsePremiumFeature } from "@/lib/entitlements";
import { getAuctionNote, setAuctionNote } from "@/lib/auction-notes";
import { downloadIcsForAuction } from "@/lib/calendar-export";
import { parseClosingMs } from "@/lib/auction-filters";
import {
  loadEmdBalance,
  lotsCoverableByBalance,
  parseEmdInr,
  saveEmdBalance,
} from "@/lib/emd-calculator";
import {
  enrichAuctionDisplay,
  materialCategoryLabel,
} from "@/lib/display-enrichment";
import { sourceLabel } from "@/lib/discovery-constants";
import { auctionCanonicalUrl } from "@/lib/seo/auction-url";
import { whatsappAlertUrl } from "@/lib/whatsapp-alert";
import { formatDateTime, resolvePublicUrl } from "@/lib/utils";
import type { AuctionRecord } from "@/types/auction";
import { cn } from "@/lib/utils";
function EmdMatrix({ auction }: { auction: AuctionRecord }) {
  const [balance, setBalance] = useState(0);
  useEffect(() => setBalance(loadEmdBalance()), []);
  if (!auction.emd_summary) return null;
  const required = parseEmdInr(auction.emd_summary);
  const cover = required ? lotsCoverableByBalance(required, balance) : null;
  return (
    <div className="rounded-lg border border-border bg-muted p-4 text-sm">
      <div className="mb-2 flex items-center gap-2 text-title text-foreground">
        <IndianRupee className="h-4 w-4 shrink-0 text-muted-foreground" />
        EMD matrix
      </div>
      <p className="tabular-nums">{auction.emd_summary}</p>
      <label className="mt-3 block text-caption">
        Your EMD balance (₹)
        <input
          type="number"
          min={0}
          className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 tabular-nums"
          value={balance || ""}
          onChange={(e) => {
            const n = Number(e.target.value) || 0;
            setBalance(n);
            saveEmdBalance(n);
          }}
        />
      </label>
      {required && balance > 0 && (
        <p className="mt-2 text-body-sm text-muted-foreground">
          You can cover up to{" "}
          <span className="tabular-nums font-medium text-foreground">
            {cover}
          </span>{" "}
          lot(s) at this EMD tier with your current balance.
        </p>
      )}
    </div>
  );
}
export function DiligencePanel({
  auction: rawAuction,
  onClose,
  searchQuery,
  className,
}: {
  auction: AuctionRecord;
  onClose: () => void;
  searchQuery?: string;
  className?: string;
}) {
  const auction = enrichAuctionDisplay(rawAuction);
  const { gateFeature } = useUpgradePrompt();
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    setNote(getAuctionNote(auction.id));
  }, [auction.id]);
  const closingMs = parseClosingMs(auction.closing);
  const snipingWindow =
    closingMs !== null &&
    closingMs > Date.now() &&
    closingMs - Date.now() < 3 * 60 * 60 * 1000;
  const staText =
    `${auction.item_summary ?? ""} ${auction.warnings?.join(" ") ?? ""}`.toLowerCase();
  const isSta =
    staText.includes("subject to approval") ||
    staText.includes("seller approval");
  const state = auction.display_location_state ?? auction.state ?? "All states";
  const material =
    materialCategoryLabel(auction.display_material_category) ?? "All materials";
  const title =
    auction.display_title ?? auction.item_summary ?? auction.auction_number;
  const lotText = auction.lots
    .map((l) =>
      [l.lot_parameters_text, l.lot_description_text]
        .filter(Boolean)
        .join("\n"),
    )
    .join("\n");
  const plantRules = extractPlantAccessRules(lotText);
  const lifting = extractLiftingWindow(lotText);
  const basePrice =
    auction.min_start_price ?? auction.lots[0]?.start_price_inr ?? null;
  const detailUrl = auctionCanonicalUrl(auction);
  const bidHref = auction.detail_url?.startsWith("http")
    ? auction.detail_url
    : auction.detail_url
      ? resolvePublicUrl(auction.detail_url)
      : null;
  const breadcrumb = useMemo(
    () => [
      { label: "Discover" },
      { label: state },
      { label: material },
      { label: auction.auction_number },
    ],
    [state, material, auction.auction_number],
  );
  const panelContent = (
    <div className="flex h-full flex-col">
      {" "}
      <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-4">
        <div className="min-w-0 space-y-2">
          <nav
            aria-label="Breadcrumb"
            className="flex flex-wrap items-center gap-1 text-caption"
          >
            {breadcrumb.map((crumb, i) => (
              <span
                key={`${crumb.label}-${i}`}
                className="inline-flex items-center gap-1"
              >
                {i > 0 && (
                  <ChevronRight className="h-3 w-3 text-muted-foreground" />
                )}
                <span
                  className={
                    i === breadcrumb.length - 1
                      ? "font-medium text-foreground"
                      : "text-muted-foreground"
                  }
                >
                  {crumb.label}
                </span>
              </span>
            ))}
          </nav>
          <h2 className="text-title text-foreground">{title}</h2>
          <div className="flex flex-wrap items-center gap-2 text-caption text-muted-foreground">
            <span>{sourceLabel(auction.source ?? "mstc")}</span>
            <span>·</span>
            <span className="tabular-nums">
              Closes {formatDateTime(auction.closing)}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="btn-secondary !min-h-[44px] !min-w-[44px] !rounded-full !p-0"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
      </header>
      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {" "}
        {snipingWindow && (
          <p className="rounded-lg border border-border bg-muted px-3 py-2 text-body-sm text-foreground">
            MSTC/GeM may extend closing on late bids (anti-sniping). Verify live
            timer on the official portal.
          </p>
        )}
        {isSta && (
          <p className="rounded-lg border border-border bg-muted px-3 py-2 text-body-sm text-foreground">
            Subject to approval (STA): seller may reject bids below internal
            reserve — confirm on source.
          </p>
        )}
        {bidHref && (
          <a
            href={bidHref}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary inline-flex w-full justify-center gap-2"
          >
            <ExternalLink className="h-4 w-4" />
            Bid on {sourceLabel(auction.source ?? "mstc")}
          </a>
        )}
        <p className="text-center text-footnote text-muted-foreground">
          Check live ranking on the official portal — this site does not execute
          bids.
        </p>
        <div className="flex flex-wrap gap-2">
          {" "}
          <button
            type="button"
            onClick={() =>
              navigator.clipboard
                .writeText(auction.id)
                .then(() => setCopied(true))
            }
            className="btn-secondary text-xs"
          >
            {" "}
            <Copy className="h-3.5 w-3.5" />{" "}
            {copied ? "Copied" : "Copy ID"}{" "}
          </button>{" "}
          <button
            type="button"
            onClick={() => window.print()}
            className="btn-secondary text-xs"
          >
            {" "}
            <Printer className="h-3.5 w-3.5" /> Print{" "}
          </button>{" "}
          <button
            type="button"
            onClick={() => downloadIcsForAuction(auction)}
            className="btn-secondary text-xs"
          >
            {" "}
            <CalendarPlus className="h-3.5 w-3.5" /> Calendar{" "}
          </button>{" "}
          <button
            type="button"
            className="btn-secondary text-xs"
            onClick={() => {
              if (
                !gateFeature(
                  "whatsapp_alert",
                  canUsePremiumFeature("whatsapp_alert"),
                  "diligence_panel",
                )
              ) {
                return;
              }
              const url = whatsappAlertUrl(
                title,
                detailUrl,
                auction.closing ?? undefined,
              );
              window.open(url, "_blank", "noopener,noreferrer");
            }}
          >
            {" "}
            <MessageCircle className="h-3.5 w-3.5" /> WhatsApp reminder{" "}
          </button>{" "}
        </div>{" "}
        <EmdMatrix auction={auction} />{" "}
        {basePrice != null && (
          <>
            <LandedCostEstimator
              basePriceInr={basePrice}
              gstPercent={parseGstPercent(auction.lots[0])}
            />
            {!canUsePremiumFeature("diligence_advanced") && (
              <button
                type="button"
                className="btn-secondary w-full text-xs"
                onClick={() =>
                  gateFeature(
                    "diligence_advanced",
                    false,
                    "diligence_landed_cost",
                  )
                }
              >
                Unlock adjustable landed-cost assumptions (Trader+)
              </button>
            )}
          </>
        )}{" "}
        <InspectionReport lots={auction.lots} />{" "}
        {lifting && (
          <p className="text-sm text-muted-foreground dark:text-muted-foreground">
            {" "}
            <span className="font-medium">Lifting window:</span> {lifting}{" "}
          </p>
        )}{" "}
        {plantRules.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {" "}
            {plantRules.map((r) => (
              <span
                key={r}
                className="rounded-full border border-border px-2 py-0.5 text-[10px] dark:border-border"
              >
                {" "}
                {r}{" "}
              </span>
            ))}{" "}
          </div>
        )}{" "}
        <LotPreviewStrip lots={auction.lots} max={6} />
        <section aria-label="Lot evidence">
          <h3 className="mb-2 text-title text-foreground">Lot details</h3>
          <LotDetails lots={auction.lots} />
        </section>
        <PostAuctionTracker auction={auction} />{" "}
        <textarea
          value={note}
          onChange={(e) => {
            setNote(e.target.value);
            setAuctionNote(auction.id, e.target.value);
          }}
          placeholder="Private notes…"
          rows={3}
          className="w-full resize-y rounded-lg border border-border bg-card px-3 py-2 text-body-sm"
        />
        <ReportIssueForm auctionId={auction.id} auctionTitle={title} />{" "}
      </div>{" "}
    </div>
  );
  return (
    <>
      {" "}
      <div
        className="fixed inset-0 z-40 hidden bg-black/20 sm:block"
        onClick={onClose}
        aria-hidden
      />{" "}
      <div
        className={cn(
          "fixed inset-0 z-50 flex flex-col bg-card sm:hidden",
          className,
        )}
        role="dialog"
        aria-modal="true"
      >
        {" "}
        {panelContent}{" "}
      </div>{" "}
      <aside
        className={cn(
          "surface-elevated fixed inset-y-0 right-0 z-50 hidden w-full max-w-[42%] min-w-[380px] shadow-2xl sm:flex sm:flex-col",
          className,
        )}
        role="dialog"
        aria-modal="true"
      >
        {" "}
        {panelContent}{" "}
      </aside>{" "}
    </>
  );
}
