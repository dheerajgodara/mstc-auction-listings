import { getValuationFields } from "@/lib/valuation";
import type { AuctionRecord } from "@/types/auction";

function csvEscape(value: string | number | null | undefined): string {
  const text = value == null ? "" : String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function auctionsToCsv(auctions: AuctionRecord[]): string {
  const headers = [
    "source",
    "auction_id",
    "source_auction_id",
    "title",
    "seller",
    "location",
    "state",
    "category",
    "price_summary",
    "emd_summary",
    "opening",
    "closing",
    "lot_count",
    "detail_url",
    "pdf_url",
    "valuation_status",
    "estimated_market_value",
  ];
  const rows = auctions.map((a) => {
    const v = getValuationFields(a);
    return [
      a.source ?? "mstc",
      a.id,
      a.source_auction_id ?? a.auction_number,
      a.item_summary ?? "",
      a.seller ?? "",
      a.location ?? a.state ?? "",
      a.state ?? "",
      a.asset_category ?? "",
      a.price_summary ?? "",
      a.emd_summary ?? "",
      a.opening ?? "",
      a.closing ?? "",
      a.lots.length,
      a.detail_url ?? "",
      a.pdf_url ?? "",
      v.valuation_status ?? "unknown",
      v.estimated_market_value ?? "",
    ]
      .map(csvEscape)
      .join(",");
  });
  return [headers.join(","), ...rows].join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
