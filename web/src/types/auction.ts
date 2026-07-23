export type EmdParseStatus =
  "auction_wise" | "item_wise" | "not_required" | "missing" | "unknown";

export type LotDocumentStatus =
  | "pending"
  | "pending_cache"
  | "downloaded"
  | "thumbnail_ready"
  | "thumbnail_failed"
  | "failed"
  | "skipped";

export type LotDocument = {
  type: "photo" | "annexure" | "document" | "unknown";
  filename: string;
  source_url?: string | null;
  cached_url?: string | null;
  thumbnail_url?: string | null;
  page_count?: number | null;
  mime_type?: string | null;
  status?: LotDocumentStatus;
  error?: string | null;
};

export interface ContactInfo {
  name?: string | null;
  phones?: string[];
  email?: string | null;
}

export type AiEnrichmentStatus =
  | "missing"
  | "pending"
  | "ready"
  | "failed"
  | "rejected"
  | "stale";

export type AiConfidence = "high" | "medium" | "low";

export interface LotRecord {
  lot_id: string;
  item_title: string;
  item_description?: string | null;
  start_price_inr?: number | null;
  start_price?: number | null;
  start_price_label?: string | null;
  start_price_text?: string | null;
  price_parse_status?: string;
  price_type?: string;
  quantity?: string | null;
  unit?: string | null;
  location?: string | null;
  lot_state?: string | null;
  gst?: string | null;
  tcs?: string | null;
  tax_text?: string | null;
  category?: string | null;
  product_type?: string | null;
  pcb_group?: string | null;
  bid_increment?: number | null;
  post_bid_emd_percent?: number | null;
  bid_valid_till?: string | null;
  pre_bid_emd_amount?: number | null;
  pre_bid_emd_text?: string | null;
  annexure_file?: string | null;
  photo_file?: string | null;
  inspection_contact?: ContactInfo | null;
  lot_details_text?: string | null;
  lot_description_text?: string | null;
  lot_parameters_text?: string | null;
  lot_other_details_text?: string | null;
  lot_documents_text?: string | null;
  lot_parse_warnings?: string[];
  documents?: LotDocument[];
  preview_images?: string[];

  ai_status?: AiEnrichmentStatus;
  ai_heading?: string | null;
  ai_summary?: string | null;
  ai_tags?: string[];
  ai_confidence?: AiConfidence | null;
  ai_model?: string | null;
  ai_generated_at?: string | null;
  ai_prompt_version?: string | null;
  ai_schema_version?: string | null;
  ai_input_hash?: string | null;
  ai_rejection_reasons?: string[];
}

export type AuctionSource = "mstc" | "eauction" | "gem_forward";

export type AssetCategory =
  | "vehicle"
  | "scrap"
  | "machinery"
  | "ewaste"
  | "minerals"
  | "timber"
  | "property"
  | "coal"
  | "other";

export interface AuctionRecord {
  id: string;
  auction_number: string;
  source?: AuctionSource;
  /** Path-safe id stamped by generate-auction-routes (collision-safe). */
  route_id?: string | null;
  source_slug?: string | null;
  source_auction_id?: string | null;
  region: string;
  office: string;
  state?: string | null;
  asset_category?: AssetCategory | null;
  platform?: string | null;
  detail_url?: string | null;
  document_urls?: string[];
  seller?: string | null;
  location?: string | null;
  office_address?: string | null;
  opening?: string | null;
  closing?: string | null;
  inspection_from?: string | null;
  inspection_to?: string | null;
  inspection?: string | null;
  pre_bid_emd_type?: string | null;
  pre_bid_emd_amount?: number | null;
  pre_bid_emd_required?: boolean | null;
  emd_parse_status?: EmdParseStatus;
  tax_summary?: string | null;
  lot_types?: string[];
  contact?: ContactInfo | null;
  seller_contact?: ContactInfo | null;
  pdf_url?: string | null;
  /** Durable Hostinger relative path (e.g. pdfs/123.pdf or docs/gem/1.pdf). */
  hostinger_doc_path?: string | null;
  /** Absolute Hostinger public URL for the durable doc (must include /auctions/). */
  hostinger_doc_url?: string | null;
  source_pdf_url?: string | null;
  mstc_html_url?: string | null;
  lots: LotRecord[];
  item_summary?: string | null;
  price_summary?: string | null;
  price_parse_status?: string;
  emd_summary?: string | null;
  min_start_price?: number | null;
  max_start_price?: number | null;
  search_text?: string;
  parse_confidence?: string;
  missing_fields?: string[];
  warnings?: string[];
  status?: string;
  errors?: string[];
  total_lots?: number | null;
  material_type?: string | null;
  estimated_market_value?: number | null;
  valuation_status?:
    | "unknown"
    | "under_market"
    | "fair"
    | "over_market"
    | "not_applicable"
    | null;
  valuation_confidence?: string | null;
  valuation_notes?: string | null;
  benchmark_source?: string | null;
  listed_at?: string | null;
  listed_date?: string | null;
  listed_at_source?:
    | "source_listed_date"
    | "published_date"
    | "created_date"
    | "catalogue_date"
    | "opening_date_fallback"
    | "missing"
    | null;
  listed_at_label?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  imported_at?: string | null;
  display_title?: string | null;
  display_location_city?: string | null;
  display_location_state?: string | null;
  display_location_raw?: string | null;
  display_quantity_summary?: string | null;
  display_material_category?: string | null;
  display_key_lots?: string[];
  display_buyer_summary?: string | null;
  display_location_confidence?: "high" | "medium" | "low" | null;
  display_total_quantity_mt?: number | null;

  ai_status?: AiEnrichmentStatus;
  ai_clean_heading?: string | null;
  ai_buyer_summary?: string | null;
  ai_clean_location_label?: string | null;
  ai_location_confidence?: AiConfidence | null;
  ai_material_tags?: string[];
  ai_buyer_intent_tags?: string[];
  ai_risk_notes?: string[];
  ai_confidence?: AiConfidence | null;
  ai_model?: string | null;
  ai_generated_at?: string | null;
  ai_prompt_version?: string | null;
  ai_schema_version?: string | null;
  ai_input_hash?: string | null;
  ai_rejection_reasons?: string[];
  /** Present on T-30 archive export rows only. */
  archive_reason?: "under_runway" | "aged_out" | "closed" | string | null;
  catalogue_status?: "none" | "pending" | "ready" | string | null;
  in_archive?: boolean | null;
}

export interface AuctionsExport {
  generated_at: string;
  export_generated_at?: string | null;
  automation_ran_at?: string | null;
  run_id?: string | null;
  count: number;
  auctions: AuctionRecord[];
  stats?: Record<string, unknown>;
  sources?: Record<
    string,
    {
      count?: number;
      lots?: number;
      status?: string;
      documents_downloaded?: number | null;
      documents_failed?: number | null;
    }
  >;
  daily_import_summary?: DailyImportSummaryRow[];
}

export interface DailyImportSummaryRow {
  date: string;
  run_id: string;
  automation_ran_at: string;
  mstc_auctions: number;
  gem_forward_auctions: number;
  eauction_auctions: number;
  total_auctions: number;
  total_lots: number;
  new_auctions_first_seen: number;
  removed_auctions: number;
  status: string;
}
