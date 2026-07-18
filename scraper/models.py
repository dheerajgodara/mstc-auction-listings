from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator


class ExtractionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    LISTING_ONLY = "listing_only"
    FAILED = "failed"


EmdParseStatus = Literal[
    "auction_wise",
    "item_wise",
    "not_required",
    "missing",
    "unknown",
]

PriceParseStatus = Literal[
    "numeric",
    "range",
    "percentage_based",
    "not_disclosed",
    "missing",
    "unknown",
]

AuctionSource = Literal["mstc", "eauction", "gem_forward"]

AssetCategory = Literal[
    "vehicle",
    "scrap",
    "machinery",
    "ewaste",
    "minerals",
    "timber",
    "property",
    "coal",
    "other",
]

AiEnrichmentStatus = Literal[
    "missing",
    "pending",
    "ready",
    "failed",
    "rejected",
    "stale",
]

AiConfidence = Literal["high", "medium", "low"]


class ContactInfo(BaseModel):
    name: Optional[str] = None
    phones: list[str] = Field(default_factory=list)
    email: Optional[str] = None


LotDocumentType = Literal["photo", "annexure", "document", "unknown"]
LotDocumentStatus = Literal[
    "pending",
    "pending_cache",
    "downloaded",
    "thumbnail_ready",
    "thumbnail_failed",
    "failed",
    "skipped",
]


class LotDocument(BaseModel):
    type: LotDocumentType = "unknown"
    filename: str
    source_url: Optional[str] = None
    cached_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    page_count: Optional[int] = None
    mime_type: Optional[str] = None
    status: LotDocumentStatus = "pending"
    error: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_document_status(cls, value: Any) -> str:
        text = str(value or "pending").strip().lower()
        allowed = {
            "pending",
            "pending_cache",
            "downloaded",
            "thumbnail_ready",
            "thumbnail_failed",
            "failed",
            "skipped",
        }
        if text in allowed:
            return text
        # Legacy / scrub aliases → pending_cache (awaiting local media sync).
        if text in {"pending-cache", "cache_pending", "not_cached", "uncached"}:
            return "pending_cache"
        return "pending"


class LotRecord(BaseModel):
    lot_id: str
    item_title: str
    item_description: Optional[str] = None
    start_price_inr: Optional[float] = None
    start_price: Optional[float] = None
    start_price_label: Optional[str] = None
    start_price_text: Optional[str] = None
    price_parse_status: PriceParseStatus = "unknown"
    price_type: str = "unknown"
    quantity: Optional[str] = None
    unit: Optional[str] = None
    location: Optional[str] = None
    lot_state: Optional[str] = None
    gst: Optional[str] = None
    tcs: Optional[str] = None
    tax_text: Optional[str] = None
    category: Optional[str] = None
    product_type: Optional[str] = None
    pcb_group: Optional[str] = None
    bid_increment: Optional[float] = None
    post_bid_emd_percent: Optional[float] = None
    bid_valid_till: Optional[str] = None
    pre_bid_emd_amount: Optional[float] = None
    pre_bid_emd_text: Optional[str] = None
    annexure_file: Optional[str] = None
    photo_file: Optional[str] = None
    inspection_contact: Optional[ContactInfo] = None
    lot_details_text: Optional[str] = None
    lot_description_text: Optional[str] = None
    lot_parameters_text: Optional[str] = None
    lot_other_details_text: Optional[str] = None
    lot_documents_text: Optional[str] = None
    lot_parse_warnings: list[str] = Field(default_factory=list)
    documents: list[LotDocument] = Field(default_factory=list)
    preview_images: list[str] = Field(default_factory=list)

    # AI buyer-facing enrichment (additive; parser fields unchanged)
    ai_status: AiEnrichmentStatus = "missing"
    ai_heading: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_tags: list[str] = Field(default_factory=list)
    ai_confidence: Optional[AiConfidence] = None
    ai_model: Optional[str] = None
    ai_generated_at: Optional[str] = None
    ai_prompt_version: Optional[str] = None
    ai_schema_version: Optional[str] = None
    ai_input_hash: Optional[str] = None
    ai_rejection_reasons: list[str] = Field(default_factory=list)


class AuctionRecord(BaseModel):
    id: str
    auction_number: str
    source: AuctionSource = "mstc"
    source_auction_id: Optional[str] = None
    region: str
    office: str
    state: Optional[str] = None
    asset_category: Optional[AssetCategory] = None
    platform: Optional[str] = None
    detail_url: Optional[str] = None
    document_urls: list[str] = Field(default_factory=list)
    seller: Optional[str] = None
    location: Optional[str] = None
    office_address: Optional[str] = None
    opening: Optional[datetime] = None
    closing: Optional[datetime] = None
    inspection_from: Optional[str] = None
    inspection_to: Optional[str] = None
    inspection: Optional[str] = None
    pre_bid_emd_type: Optional[str] = None
    pre_bid_emd_amount: Optional[float] = None
    pre_bid_emd_required: Optional[bool] = None
    emd_parse_status: EmdParseStatus = "unknown"
    tax_summary: Optional[str] = None
    lot_types: list[str] = Field(default_factory=list)
    contact: Optional[ContactInfo] = None
    seller_contact: Optional[ContactInfo] = None
    pdf_url: Optional[str] = None
    source_pdf_url: Optional[str] = None
    mstc_html_url: Optional[str] = None
    lots: list[LotRecord] = Field(default_factory=list)
    item_summary: Optional[str] = None
    price_summary: Optional[str] = None
    price_parse_status: PriceParseStatus = "unknown"
    emd_summary: Optional[str] = None
    min_start_price: Optional[float] = None
    max_start_price: Optional[float] = None
    search_text: str = ""
    parse_confidence: str = "low"
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: ExtractionStatus = ExtractionStatus.LISTING_ONLY
    errors: list[str] = Field(default_factory=list)
    total_lots: Optional[int] = None

    # Enlistment / listed date (optional; populated only when the source exposes it)
    listed_at: Optional[datetime] = None
    listed_date: Optional[str] = None
    listed_at_source: Literal[
        "source_listed_date",
        "published_date",
        "created_date",
        "catalogue_date",
        "opening_date_fallback",
        "missing",
    ] = "missing"
    listed_at_label: Optional[str] = None

    # Import / first-seen tracking (our dataset, not source listed date)
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    imported_at: Optional[datetime] = None

    # Buyer-facing display enrichment (additive; raw fields unchanged)
    display_title: Optional[str] = None
    display_location_city: Optional[str] = None
    display_location_state: Optional[str] = None
    display_location_raw: Optional[str] = None
    display_quantity_summary: Optional[str] = None
    display_material_category: Optional[str] = None
    display_key_lots: list[str] = Field(default_factory=list)
    display_buyer_summary: Optional[str] = None
    display_location_confidence: Optional[str] = None
    display_total_quantity_mt: Optional[float] = None

    # AI buyer-facing enrichment (additive; parser/raw fields unchanged)
    ai_status: AiEnrichmentStatus = "missing"
    ai_clean_heading: Optional[str] = None
    ai_buyer_summary: Optional[str] = None
    ai_clean_location_label: Optional[str] = None
    ai_location_confidence: Optional[AiConfidence] = None
    ai_material_tags: list[str] = Field(default_factory=list)
    ai_buyer_intent_tags: list[str] = Field(default_factory=list)
    ai_risk_notes: list[str] = Field(default_factory=list)
    ai_confidence: Optional[AiConfidence] = None
    ai_model: Optional[str] = None
    ai_generated_at: Optional[str] = None
    ai_prompt_version: Optional[str] = None
    ai_schema_version: Optional[str] = None
    ai_input_hash: Optional[str] = None
    ai_rejection_reasons: list[str] = Field(default_factory=list)

    @field_serializer("opening", "closing", "listed_at", "first_seen_at", "last_seen_at", "imported_at")
    def serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        return v.isoformat() if v else None


class ListingApiAuction(BaseModel):
    id: str
    text: str
    opening: str
    Closing: str
    GeneralLots: str
    RVSFLots: str
    HazardousWaste: str
    OFF_NAME: str
    region: str


class ListingApiOfficeResponse(BaseModel):
    MSG: str = ""
    OFFICE: str
    REGION: str
    auction: list[ListingApiAuction] = Field(default_factory=list)


class AuctionsExport(BaseModel):
    generated_at: datetime
    export_generated_at: Optional[datetime] = None
    automation_ran_at: Optional[datetime] = None
    run_id: Optional[str] = None
    count: int
    auctions: list[AuctionRecord]
    stats: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, Any] = Field(default_factory=dict)
    daily_import_summary: list[dict[str, Any]] = Field(default_factory=list)

    @field_serializer("generated_at", "export_generated_at", "automation_ran_at")
    def serialize_generated(self, v: Optional[datetime]) -> Optional[str]:
        return v.isoformat() if v else None
