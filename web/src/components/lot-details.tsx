"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Chip, Input } from "@/components/ui/primitives";
import {
  formatInrOrDash,
  formatLotPrice,
  formatPercentOrLabel,
  formatPreBidEmd,
  formatQuantityUnit,
  getLotSectionDisplayText,
  isHttpUrl,
  matchesLotSearch,
} from "@/lib/format";
import { formatDateTime } from "@/lib/utils";
import type { LotRecord } from "@/types/auction";
import { LotDocumentsPanel } from "@/components/lot-documents";

const INITIAL_LOT_COUNT = 10;

const RAW_SECTION_KEYS = [
  "lot_details_text",
  "lot_description_text",
  "lot_parameters_text",
  "lot_other_details_text",
  "lot_documents_text",
] as const;

function hasLotSectionContent(
  lot: LotRecord,
  key: (typeof RAW_SECTION_KEYS)[number]
): boolean {
  return getLotSectionDisplayText(lot, key) !== "Not available";
}

function LotField({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value || value === "—") return null;
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 break-words text-sm text-slate-800">{value}</dd>
    </div>
  );
}

function RawSection({ label, text }: { label: string; text: string }) {
  const unavailable = text === "Not available";
  return (
    <div className="min-w-0">
      <h5 className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">
        {label}
      </h5>
      <pre
        className={`mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-white/60 bg-white/50 p-2 text-xs leading-relaxed text-slate-800 ${
          unavailable ? "italic text-slate-500" : "font-mono"
        }`}
      >
        {text}
      </pre>
    </div>
  );
}

function FileChip({ label, filename }: { label: string; filename: string }) {
  if (isHttpUrl(filename)) {
    return (
      <a
        href={filename}
        target="_blank"
        rel="noopener noreferrer"
        className="btn-glass px-2 py-1 text-xs"
      >
        {label}
      </a>
    );
  }
  return (
    <Chip className="border-slate-200/80 bg-white/70 text-slate-700 normal-case tracking-normal">
      {label}: {filename}
    </Chip>
  );
}

function LotCard({ lot }: { lot: LotRecord }) {
  const [fullOpen, setFullOpen] = useState(false);
  const qty = formatQuantityUnit(lot.quantity, lot.unit);
  const hasFiles = Boolean(lot.annexure_file?.trim() || lot.photo_file?.trim());
  const hasRawSections =
    RAW_SECTION_KEYS.some((key) => hasLotSectionContent(lot, key)) ||
    Boolean(lot.lot_parse_warnings?.length);

  return (
    <article className="rounded-lg border border-white/60 bg-white/55 p-3 backdrop-blur-sm">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-900">Lot {lot.lot_id}</h4>
        {lot.item_title && lot.item_title !== lot.lot_id && (
          <span className="text-sm text-slate-600">{lot.item_title}</span>
        )}
      </div>

      {lot.item_description && (
        <p className="mb-3 line-clamp-2 text-sm text-slate-600">
          {lot.item_description}
        </p>
      )}

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <LotField label="Quantity" value={qty} />
        <LotField label="Start / floor price" value={formatLotPrice(lot)} />
        <LotField label="Pre-bid EMD" value={formatPreBidEmd(lot)} />
        <LotField label="GST" value={formatPercentOrLabel(lot.gst)} />
        <LotField label="TCS" value={formatPercentOrLabel(lot.tcs)} />
        <LotField label="Location" value={lot.location} />
        <LotField
          label="Bid increment"
          value={
            lot.bid_increment != null ? formatInrOrDash(lot.bid_increment) : null
          }
        />
        <LotField
          label="Bid valid till"
          value={lot.bid_valid_till ? formatDateTime(lot.bid_valid_till) : null}
        />
      </dl>

      {hasFiles && (
        <div className="mt-3 flex flex-wrap gap-2">
          {lot.annexure_file?.trim() && (
            <FileChip label="Annexure" filename={lot.annexure_file.trim()} />
          )}
          {lot.photo_file?.trim() && (
            <FileChip label="Photo" filename={lot.photo_file.trim()} />
          )}
        </div>
      )}

      {lot.lot_parse_warnings && lot.lot_parse_warnings.length > 0 && (
        <p className="mt-2 text-xs text-amber-800">
          Parse notes: {lot.lot_parse_warnings.join(", ")}
        </p>
      )}

      <LotDocumentsPanel lot={lot} />

      {hasRawSections && (
        <div className="mt-3 border-t border-white/50 pt-3">
          <button
            type="button"
            onClick={() => setFullOpen((v) => !v)}
            className="btn-glass w-full text-sm"
          >
            {fullOpen ? "Hide full lot data" : "Show full lot data"}
          </button>
          {fullOpen && (
            <div className="mt-3 space-y-3">
              {(
                [
                  ["lot_details_text", "Lot Details"],
                  ["lot_description_text", "Lot Description"],
                  ["lot_parameters_text", "Lot Parameters"],
                  ["lot_other_details_text", "Other Details"],
                  ["lot_documents_text", "Lot Documents"],
                ] as const
              ).map(([key, label]) => (
                <RawSection
                  key={key}
                  label={label}
                  text={getLotSectionDisplayText(lot, key)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export function LotDetails({ lots }: { lots: LotRecord[] }) {
  const [open, setOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return lots;
    return lots.filter((lot) => matchesLotSearch(lot, search));
  }, [lots, search]);

  const visibleLots = showAll
    ? filtered
    : filtered.slice(0, INITIAL_LOT_COUNT);

  const toggleOpen = () => {
    setOpen((v) => {
      if (v) {
        setShowAll(false);
        setSearch("");
      }
      return !v;
    });
  };

  if (lots.length === 0) {
    return (
      <p className="border-t border-white/50 pt-3 text-xs text-slate-500">
        No lot details available
      </p>
    );
  }

  const countLabel = `(${lots.length})`;

  return (
    <div className="border-t border-white/50 pt-3">
      <button
        type="button"
        onClick={toggleOpen}
        className="btn-glass flex w-full items-center justify-between px-3 py-2"
      >
        <span>{open ? `Hide lots ${countLabel}` : `View lots ${countLabel}`}</span>
        {open ? (
          <ChevronUp className="h-4 w-4 shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0" />
        )}
      </button>

      {open && (
        <div className="glass-nested mt-3 space-y-3 p-3">
          {lots.length > 5 && (
            <Input
              type="search"
              placeholder="Search lots"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-9"
            />
          )}

          {filtered.length === 0 ? (
            <p className="text-sm text-slate-600">No lots match your search.</p>
          ) : (
            <>
              <div className="space-y-3">
                {visibleLots.map((lot) => (
                  <LotCard key={lot.lot_id} lot={lot} />
                ))}
              </div>

              {filtered.length > INITIAL_LOT_COUNT && (
                <button
                  type="button"
                  onClick={() => setShowAll((v) => !v)}
                  className="btn-glass w-full text-sm"
                >
                  {showAll
                    ? "Show first 10"
                    : `Show all lots (${filtered.length})`}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
