import type { LotRecord } from "@/types/auction";

/** INR with Indian grouping; returns em dash when missing (lot detail context). */
export function formatInrOrDash(amount: number | null | undefined): string {
  if (amount == null) return "—";
  if (amount <= 1) return "₹1";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

/** Percent or tax label; numbers become `N%`, text shown as-is. */
export function formatPercentOrLabel(
  value: number | string | null | undefined,
): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number") return `${value}%`;
  const s = String(value).trim();
  return s || "—";
}

export function formatQuantityUnit(
  quantity: string | null | undefined,
  unit: string | null | undefined,
): string | null {
  const q = quantity?.trim();
  const u = unit?.trim();
  if (q && u && !q.toUpperCase().includes(u.toUpperCase())) return `${q} ${u}`;
  if (q) return q;
  if (u) return u;
  return null;
}

export function formatLotPrice(lot: LotRecord): string {
  if (lot.start_price_label?.trim()) return lot.start_price_label.trim();
  if (lot.start_price_text?.trim()) return lot.start_price_text.trim();
  const amount = lot.start_price_inr ?? lot.start_price;
  if (amount != null) return formatInrOrDash(amount);
  return "—";
}

export function formatPreBidEmd(lot: LotRecord): string {
  if (lot.pre_bid_emd_text?.trim()) return lot.pre_bid_emd_text.trim();
  if (lot.pre_bid_emd_amount != null) return formatInrOrDash(lot.pre_bid_emd_amount);
  return "—";
}

export function isHttpUrl(value: string): boolean {
  return value.startsWith("http://") || value.startsWith("https://");
}

type LotSectionKey =
  | "lot_details_text"
  | "lot_description_text"
  | "lot_parameters_text"
  | "lot_other_details_text"
  | "lot_documents_text";

function hasText(value: string | null | undefined): boolean {
  return Boolean(value && value.trim());
}

function synthesizeLotSectionText(lot: LotRecord, key: LotSectionKey): string | null {
  if (key === "lot_details_text") {
    const lines: string[] = [];
    if (lot.lot_id) lines.push(`Lot No - ${lot.lot_id}`);
    if (lot.item_title && lot.item_title !== lot.lot_id) {
      lines.push(`Lot Name - ${lot.item_title}`);
    }
    if (lot.product_type) lines.push(`Product Type - ${lot.product_type}`);
    if (lot.category) lines.push(`Category - ${lot.category}`);
    if (lot.pcb_group) lines.push(`PCB Group - ${lot.pcb_group}`);
    return lines.length ? lines.join("\n") : null;
  }

  if (key === "lot_description_text") {
    return lot.item_description?.trim() || null;
  }

  if (key === "lot_parameters_text") {
    const lines: string[] = [];
    if (lot.quantity) lines.push(`Quantity - ${lot.quantity}`);
    if (lot.start_price_text) {
      if (
        lot.start_price_text.toUpperCase().includes("PER") ||
        lot.start_price_text.includes("%")
      ) {
        const m = lot.start_price_text.replace(/^Premium\s*/i, "").replace(/%$/, "").trim();
        lines.push(`Start Price in PER - ${m}`);
      } else {
        lines.push(`Start Price - ${lot.start_price_text}`);
      }
    } else if (lot.start_price != null) {
      lines.push(`Start Price in INR - ${Math.trunc(lot.start_price)}`);
    } else if (lot.start_price_inr != null) {
      lines.push(`Start Price in INR - ${Math.trunc(lot.start_price_inr)}`);
    }
    if (lot.bid_increment != null) {
      lines.push(`Bid Increment in INR - ${lot.bid_increment}`);
    }
    if (lot.post_bid_emd_percent != null) {
      lines.push(`Post Bid EMD % - ${lot.post_bid_emd_percent}`);
    }
    if (lot.tcs) lines.push(`TCS (%) - ${lot.tcs}`);
    if (lot.pre_bid_emd_text) lines.push(`Pre-Bid EMD Amount - ${lot.pre_bid_emd_text}`);
    else if (lot.pre_bid_emd_amount != null) {
      lines.push(`Pre-Bid EMD Amount - ${lot.pre_bid_emd_amount}`);
    }
    return lines.length ? lines.join("\n") : null;
  }

  if (key === "lot_other_details_text") {
    const lines: string[] = [];
    if (lot.gst) lines.push(`GST (%) - ${lot.gst}`);
    if (lot.location) lines.push(`Lot Location - ${lot.location}`);
    if (lot.lot_state) lines.push(`Lot State - ${lot.lot_state}`);
    if (lot.bid_valid_till) lines.push(`Bid Valid Till - ${lot.bid_valid_till}`);
    return lines.length ? lines.join("\n") : null;
  }

  if (key === "lot_documents_text") {
    const lines: string[] = [];
    if (lot.annexure_file) {
      lines.push(`Annexure for Lot no ${lot.lot_id || "1"} - ${lot.annexure_file}`);
    }
    if (lot.photo_file) {
      lines.push(`Photo for Lot no ${lot.lot_id || "1"} - ${lot.photo_file}`);
    }
    return lines.length ? lines.join("\n") : null;
  }

  return null;
}

export function getLotSectionDisplayText(lot: LotRecord, key: LotSectionKey): string {
  const raw = lot[key];
  if (hasText(raw)) return raw!.trim();
  const synthesized = synthesizeLotSectionText(lot, key);
  if (hasText(synthesized)) return synthesized!.trim();
  return "Not available";
}

export function matchesLotSearch(lot: LotRecord, query: string): boolean {
  if (!query.trim()) return true;
  const needle = query.toLowerCase();
  const hay = [
    lot.lot_id,
    lot.item_title,
    lot.item_description,
    lot.location,
    lot.category,
    lot.product_type,
    lot.lot_details_text,
    lot.lot_description_text,
    lot.lot_parameters_text,
    lot.lot_other_details_text,
    lot.lot_documents_text,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(needle);
}
