from __future__ import annotations

import logging
import re
from typing import Any, Optional

from scraper.display_enrichment import apply_display_enrichment, build_display_search_text
from scraper.emd import classify_emd_type_text, format_inr_amount
from scraper.lot_sections import synthesize_lot_sections
from scraper.models import AuctionRecord, ContactInfo, EmdParseStatus, ExtractionStatus, LotRecord, PriceParseStatus
from scraper.price import classify_lot_price, detect_price_signal, price_satisfied, resolve_auction_price

logger = logging.getLogger(__name__)


def _norm_lot_id(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value)).upper()

def _price_type(amount: float | int | None) -> str:
    if amount is None:
        return "unknown"
    return "open_bidding" if amount <= 1 else "fixed_floor"


def html_lot_to_record(lot: dict[str, Any]) -> LotRecord:
    qty = lot.get("quantity")
    unit = lot.get("unit")
    quantity = f"{qty} {unit}".strip() if qty and unit else qty or unit
    contact = None
    if lot.get("inspection_contact"):
        c = lot["inspection_contact"]
        contact = ContactInfo(
            name=c.get("name"),
            phones=c.get("phones") or [],
            email=c.get("email"),
        )
    desc = lot.get("description")
    start_price_text = None
    price_status: PriceParseStatus = "unknown"
    if desc and detect_price_signal(desc):
        start_price_text = desc
        price_status = detect_price_signal(desc) or "unknown"
    return LotRecord(
        lot_id=str(lot.get("lot_no") or ""),
        item_title=lot.get("name") or "Unknown item",
        item_description=desc,
        lot_description_text=desc,
        start_price_text=start_price_text,
        price_parse_status=price_status,
        quantity=quantity,
        unit=unit,
        location=lot.get("location"),
        tax_text=lot.get("tax_text"),
        gst=lot.get("tax_text"),
        inspection_contact=contact,
    )


def pdf_lot_to_record(lot: dict[str, Any]) -> LotRecord:
    from scraper.text_cleanup import cleanup_ocr_text

    start_price = lot.get("start_price")
    if start_price is not None:
        start_price = float(start_price)
    extra = " ".join(
        filter(None, [lot.get("lot_name"), lot.get("category"), lot.get("pcb_group"), lot.get("start_price_text")])
    )
    lot_price_status = classify_lot_price(
        start_price_inr=start_price,
        start_price_text=lot.get("start_price_text"),
        extra_text=extra,
    )
    return LotRecord(
        lot_id=str(lot.get("lot_no") or ""),
        item_title=lot.get("lot_name") or lot.get("lot_no") or "Unknown item",
        item_description=cleanup_ocr_text(lot.get("item_description")),
        start_price_inr=start_price,
        start_price=start_price,
        start_price_label=lot.get("start_price_label"),
        start_price_text=lot.get("start_price_text"),
        price_parse_status=lot_price_status,
        price_type=_price_type(start_price),
        quantity=lot.get("quantity"),
        unit=lot.get("unit"),
        location=lot.get("lot_location"),
        lot_state=lot.get("lot_state"),
        category=lot.get("category"),
        product_type=lot.get("product_type"),
        pcb_group=lot.get("pcb_group"),
        bid_increment=lot.get("bid_increment"),
        post_bid_emd_percent=lot.get("post_bid_emd_percent"),
        tcs=str(lot.get("tcs_percent")) if lot.get("tcs_percent") is not None else lot.get("gst_text"),
        gst=lot.get("gst_text") or (str(lot.get("gst_percent")) if lot.get("gst_percent") is not None else None),
        bid_valid_till=lot.get("bid_valid_till"),
        pre_bid_emd_amount=lot.get("pre_bid_emd_amount"),
        pre_bid_emd_text=lot.get("pre_bid_emd_text"),
        annexure_file=lot.get("annexure_file"),
        photo_file=lot.get("photo_file"),
        lot_details_text=cleanup_ocr_text(lot.get("lot_details_text")),
        lot_description_text=cleanup_ocr_text(lot.get("lot_description_text")),
        lot_parameters_text=cleanup_ocr_text(lot.get("lot_parameters_text")),
        lot_other_details_text=cleanup_ocr_text(lot.get("lot_other_details_text")),
        lot_documents_text=cleanup_ocr_text(lot.get("lot_documents_text")),
        lot_parse_warnings=lot.get("lot_parse_warnings") or [],
    )


def _merge_description_text(html_lot: LotRecord, pdf_lot: LotRecord) -> str | None:
    if pdf_lot.lot_description_text:
        return pdf_lot.lot_description_text
    if html_lot.lot_description_text:
        return html_lot.lot_description_text
    if html_lot.item_description:
        return html_lot.item_description
    return None


def _merge_lot(html_lot: LotRecord | None, pdf_lot: LotRecord | None) -> LotRecord:
    if html_lot and pdf_lot:
        return LotRecord(
            lot_id=html_lot.lot_id or pdf_lot.lot_id,
            item_title=html_lot.item_title or pdf_lot.item_title,
            item_description=html_lot.item_description or pdf_lot.item_description,
            start_price_inr=pdf_lot.start_price_inr if pdf_lot.start_price_inr is not None else html_lot.start_price_inr,
            start_price=pdf_lot.start_price if pdf_lot.start_price is not None else html_lot.start_price,
            start_price_label=pdf_lot.start_price_label or html_lot.start_price_label,
            start_price_text=pdf_lot.start_price_text or html_lot.start_price_text,
            price_type=pdf_lot.price_type if pdf_lot.price_type != "unknown" else html_lot.price_type,
            quantity=html_lot.quantity or pdf_lot.quantity,
            unit=html_lot.unit or pdf_lot.unit,
            location=html_lot.location or pdf_lot.location,
            lot_state=pdf_lot.lot_state,
            gst=html_lot.gst or pdf_lot.gst,
            tcs=pdf_lot.tcs,
            tax_text=html_lot.tax_text or pdf_lot.gst,
            category=pdf_lot.category or html_lot.category,
            product_type=pdf_lot.product_type,
            pcb_group=pdf_lot.pcb_group,
            bid_increment=pdf_lot.bid_increment,
            post_bid_emd_percent=pdf_lot.post_bid_emd_percent,
            bid_valid_till=pdf_lot.bid_valid_till,
            pre_bid_emd_amount=pdf_lot.pre_bid_emd_amount if pdf_lot.pre_bid_emd_amount is not None else html_lot.pre_bid_emd_amount,
            pre_bid_emd_text=pdf_lot.pre_bid_emd_text or html_lot.pre_bid_emd_text,
            annexure_file=pdf_lot.annexure_file,
            photo_file=pdf_lot.photo_file,
            lot_details_text=pdf_lot.lot_details_text or html_lot.lot_details_text,
            lot_description_text=_merge_description_text(html_lot, pdf_lot),
            lot_parameters_text=pdf_lot.lot_parameters_text or html_lot.lot_parameters_text,
            lot_other_details_text=pdf_lot.lot_other_details_text or html_lot.lot_other_details_text,
            lot_documents_text=pdf_lot.lot_documents_text or html_lot.lot_documents_text,
            lot_parse_warnings=pdf_lot.lot_parse_warnings or html_lot.lot_parse_warnings,
            inspection_contact=html_lot.inspection_contact or pdf_lot.inspection_contact,
        )
    return html_lot or pdf_lot or LotRecord(lot_id="unknown", item_title="Unknown item")


def _finalize_lot(lot: LotRecord) -> LotRecord:
    return synthesize_lot_sections(lot)


def merge_lots(
    html_lots: list[dict[str, Any]] | list[LotRecord],
    pdf_lots: list[dict[str, Any]] | list[LotRecord],
) -> list[LotRecord]:
    html_records = [
        l if isinstance(l, LotRecord) else html_lot_to_record(l) for l in html_lots
    ]
    pdf_records = [
        l if isinstance(l, LotRecord) else pdf_lot_to_record(l) for l in pdf_lots
    ]

    pdf_by_id = {_norm_lot_id(l.lot_id): l for l in pdf_records if l.lot_id}
    used_pdf: set[str] = set()
    merged: list[LotRecord] = []

    for i, html_lot in enumerate(html_records):
        key = _norm_lot_id(html_lot.lot_id)
        pdf_lot = pdf_by_id.get(key)
        if pdf_lot:
            used_pdf.add(key)
        elif i < len(pdf_records):
            pdf_lot = pdf_records[i]
            used_pdf.add(_norm_lot_id(pdf_lot.lot_id))
        merged.append(_finalize_lot(_merge_lot(html_lot, pdf_lot)))

    for pdf_lot in pdf_records:
        key = _norm_lot_id(pdf_lot.lot_id)
        if key and key not in used_pdf:
            merged.append(_finalize_lot(pdf_lot))

    return merged


def _lot_has_emd(lots: list[LotRecord]) -> bool:
    emd_pattern = re.compile(r"pre[- ]?bid\s+emd|emd\s+amount", re.I)
    for lot in lots:
        if lot.pre_bid_emd_amount is not None or bool(lot.pre_bid_emd_text):
            return True
        section_text = " ".join(
            filter(
                None,
                [
                    lot.lot_details_text,
                    lot.lot_parameters_text,
                    lot.lot_description_text,
                    lot.item_description,
                ],
            )
        )
        if emd_pattern.search(section_text):
            return True
    return False


def _lot_emd_amounts(lots: list[LotRecord]) -> list[float]:
    return [l.pre_bid_emd_amount for l in lots if l.pre_bid_emd_amount is not None]


def resolve_auction_emd(
    *,
    html_data: dict[str, Any] | None,
    pdf_header: dict[str, Any] | None,
    lots: list[LotRecord],
) -> tuple[
    Optional[str],
    Optional[float],
    Optional[bool],
    EmdParseStatus,
]:
    emd_type: Optional[str] = None
    emd_amount: Optional[float] = None
    emd_required: Optional[bool] = None
    emd_status: EmdParseStatus = "unknown"

    if html_data:
        emd_type = html_data.get("pre_bid_emd_type")
        emd_amount = html_data.get("pre_bid_emd_amount")
        emd_required = html_data.get("pre_bid_emd_required")
        emd_status = html_data.get("emd_parse_status", "unknown")

    if pdf_header:
        if not emd_type:
            emd_type = pdf_header.get("pre_bid_emd_type")
        if emd_amount is None:
            emd_amount = pdf_header.get("pre_bid_emd_amount")
        if emd_required is None:
            emd_required = pdf_header.get("pre_bid_emd_required")
        pdf_status = pdf_header.get("emd_parse_status", "unknown")
        if emd_status == "unknown" and pdf_status != "unknown":
            emd_status = pdf_status
        elif html_data is None and pdf_status != "unknown":
            emd_status = pdf_status

    if html_data and html_data.get("emd_parse_status") not in (None, "unknown", "missing"):
        emd_status = html_data["emd_parse_status"]
        emd_required = html_data.get("pre_bid_emd_required")
        if html_data.get("pre_bid_emd_type"):
            emd_type = html_data["pre_bid_emd_type"]

    if emd_type:
        type_required, type_status = classify_emd_type_text(emd_type)
        if type_status in ("item_wise", "auction_wise", "not_required"):
            emd_status = type_status
            if type_required is not None:
                emd_required = type_required
        elif emd_status in ("unknown", "missing"):
            emd_status = type_status
            if type_required is not None:
                emd_required = type_required

    lot_amounts = _lot_emd_amounts(lots)
    lot_has_emd = _lot_has_emd(lots)

    if emd_status == "not_required":
        emd_required = False
    elif emd_status == "auction_wise":
        emd_required = True
        if emd_amount is None and lot_amounts:
            emd_amount = lot_amounts[0]
    elif emd_status == "item_wise":
        emd_required = True
    elif lot_has_emd:
        emd_required = True
        emd_status = "item_wise"
    elif emd_amount is not None:
        emd_required = True
        emd_status = "auction_wise"
    elif emd_required is True:
        emd_status = "missing"
    elif emd_required is False:
        emd_status = "not_required"
    else:
        emd_status = "unknown"

    if emd_type and classify_emd_type_text(emd_type)[1] == "item_wise":
        emd_status = "item_wise"
        emd_required = True

    return emd_type, emd_amount, emd_required, emd_status


def build_item_summary(lots: list[LotRecord]) -> str | None:
    if not lots:
        return None
    names = [l.item_title for l in lots[:3] if l.item_title]
    if not names:
        return None
    summary = "; ".join(names)
    if len(lots) > 3:
        summary += f" (+{len(lots) - 3} more)"
    return summary


def build_lot_count_warnings(html_count: int, pdf_count: int) -> list[str]:
    warnings: list[str] = []
    if html_count == 0 and pdf_count == 0:
        warnings.append("No lots found in HTML or PDF")
        return warnings
    if html_count > 0 and pdf_count > 0 and html_count != pdf_count:
        lo, hi = min(html_count, pdf_count), max(html_count, pdf_count)
        if hi - lo >= 5 and hi / lo >= 1.5:
            warnings.append(f"lot_count_mismatch: html={html_count} pdf={pdf_count}")
    return warnings


def build_price_summary(lots: list[LotRecord]) -> str | None:
    status, summary = resolve_auction_price(lots)
    return summary


def build_emd_summary(
    emd_status: EmdParseStatus,
    auction_emd: Optional[float],
    lots: list[LotRecord],
) -> str | None:
    if emd_status == "not_required":
        return "No auto pre-bid EMD"
    if emd_status == "missing":
        return "EMD not found"

    lot_amounts = _lot_emd_amounts(lots)
    lot_texts = [l.pre_bid_emd_text for l in lots if l.pre_bid_emd_text]

    if emd_status == "auction_wise":
        if auction_emd is not None:
            return f"Pre-bid EMD: {format_inr_amount(auction_emd)} auction-wise"
        return "Pre-bid EMD: auction-wise"

    if emd_status == "item_wise":
        if lot_amounts:
            lo = min(lot_amounts)
            return f"Pre-bid EMD: item-wise, from {format_inr_amount(lo)}"
        if lot_texts:
            return "Pre-bid EMD: item-wise"
        return "Pre-bid EMD: item-wise"

    if auction_emd is not None:
        return f"Pre-bid EMD: {format_inr_amount(auction_emd)}"
    if lot_amounts:
        lo = min(lot_amounts)
        return f"Pre-bid EMD: item-wise, from {format_inr_amount(lo)}"
    if lot_texts:
        return "Pre-bid EMD: item-wise"
    return None


def build_tax_summary(lots: list[LotRecord]) -> str | None:
    gst_vals: set[str] = set()
    tcs_vals: set[str] = set()
    for lot in lots:
        if lot.gst:
            gst_vals.add(lot.gst.replace("GST", "").strip(" /:"))
        if lot.tcs:
            tcs_vals.add(str(lot.tcs))
        if lot.tax_text and not lot.gst:
            gst_vals.add(lot.tax_text)
    parts: list[str] = []
    if gst_vals:
        parts.append("GST " + ", ".join(sorted(gst_vals)))
    if tcs_vals:
        parts.append("TCS " + ", ".join(sorted(tcs_vals)))
    return "; ".join(parts) if parts else None


def emd_satisfied(record: AuctionRecord) -> bool:
    if record.emd_parse_status == "not_required":
        return True
    if record.emd_parse_status == "item_wise":
        return True
    if record.emd_parse_status == "auction_wise" and record.pre_bid_emd_amount is not None:
        return True
    if record.emd_parse_status == "item_wise":
        return _lot_has_emd(record.lots)
    if record.pre_bid_emd_amount is not None:
        return True
    return _lot_has_emd(record.lots)


def compute_missing_fields(record: AuctionRecord) -> list[str]:
    missing: list[str] = []
    if not record.location:
        missing.append("location")
    if not record.seller:
        missing.append("seller")
    if not record.lots:
        missing.append("lots")
    if record.price_parse_status == "missing":
        missing.append("start_price")

    emd_missing = False
    if record.emd_parse_status not in {"not_required", "item_wise"}:
        needs_emd = record.pre_bid_emd_required is True or record.pre_bid_emd_required is None
        has_auction_emd = record.pre_bid_emd_amount is not None
        has_lot_emd = _lot_has_emd(record.lots)
        if needs_emd and not has_auction_emd and not has_lot_emd:
            emd_missing = True
    if emd_missing:
        missing.append("emd")

    if not record.opening:
        missing.append("opening")
    if not record.closing:
        missing.append("closing")
    return missing


def compute_parse_confidence(record: AuctionRecord) -> str:
    if not record.lots:
        return "low"
    has_location = bool(record.location)
    has_lots = bool(record.lots)
    has_price = price_satisfied(record.price_parse_status)
    has_emd = emd_satisfied(record)
    if has_location and has_lots and has_price and has_emd:
        return "high"
    if has_location and has_lots and (has_price or has_emd):
        return "medium"
    if has_lots or has_location:
        return "low"
    return "minimal"


def build_search_text(record: AuctionRecord) -> str:
    parts: list[str] = [
        record.seller or "",
        record.location or "",
        record.office_address or "",
        record.state or "",
        record.item_summary or "",
    ]
    for lot in record.lots:
        parts.extend([
            lot.item_title,
            lot.item_description or "",
            lot.location or "",
            lot.category or "",
            lot.product_type or "",
            lot.lot_details_text or "",
            lot.lot_description_text or "",
            lot.lot_parameters_text or "",
            lot.lot_other_details_text or "",
            lot.lot_documents_text or "",
            " ".join(doc.filename for doc in lot.documents),
        ])
    return " ".join(p.lower() for p in parts if p)


def merge_auction_record(
    base: AuctionRecord,
    html_data: dict[str, Any] | None = None,
    pdf_lots: list[dict[str, Any]] | None = None,
    pdf_header: dict[str, Any] | None = None,
    pdf_relative_url: str | None = None,
    source_pdf_url: str | None = None,
) -> AuctionRecord:
    errors = list(base.errors)
    html_lot_dicts: list[dict[str, Any]] = []
    html_lot_count = 0
    pdf_lot_count = len(pdf_lots) if pdf_lots else 0
    warnings: list[str] = []
    status = base.status

    if html_data:
        base.auction_number = html_data.get("auction_number") or base.auction_number
        base.seller = html_data.get("seller") or base.seller
        base.location = html_data.get("location") or base.location
        base.office_address = html_data.get("office_address") or base.office_address
        base.inspection_from = html_data.get("inspection_from")
        base.inspection_to = html_data.get("inspection_to")
        if base.inspection_from and base.inspection_to:
            base.inspection = f"{base.inspection_from} to {base.inspection_to}"
        contact = html_data.get("seller_contact") or html_data.get("contact")
        if contact:
            base.seller_contact = ContactInfo(**contact) if isinstance(contact, dict) else contact
            base.contact = base.seller_contact
        base.mstc_html_url = html_data.get("mstc_html_url") or base.mstc_html_url
        if html_data.get("total_lots"):
            try:
                base.total_lots = int(re.sub(r"\D", "", str(html_data["total_lots"])) or 0) or None
            except ValueError:
                pass
        html_lot_dicts = html_data.get("lots") or []
        html_lot_count = len(html_lot_dicts)
        status = ExtractionStatus.PARTIAL

    warnings.extend(build_lot_count_warnings(html_lot_count, pdf_lot_count))

    if pdf_lots:
        base.lots = merge_lots(html_lot_dicts, pdf_lots) if html_lot_dicts else [
            _finalize_lot(pdf_lot_to_record(l)) for l in pdf_lots
        ]
        prices = [l.start_price_inr for l in base.lots if l.start_price_inr is not None]
        if prices:
            base.min_start_price = float(min(prices))
            base.max_start_price = float(max(prices))
        status = ExtractionStatus.COMPLETE if html_lot_dicts else ExtractionStatus.PARTIAL
    elif html_lot_dicts:
        base.lots = [_finalize_lot(html_lot_to_record(l)) for l in html_lot_dicts]
        status = ExtractionStatus.PARTIAL

    emd_type, emd_amount, emd_required, emd_status = resolve_auction_emd(
        html_data=html_data,
        pdf_header=pdf_header,
        lots=base.lots,
    )
    base.pre_bid_emd_type = emd_type
    base.pre_bid_emd_amount = emd_amount
    base.pre_bid_emd_required = emd_required
    base.emd_parse_status = emd_status

    if pdf_relative_url:
        base.pdf_url = pdf_relative_url
    if source_pdf_url:
        base.source_pdf_url = source_pdf_url

    base.item_summary = build_item_summary(base.lots)
    price_status, price_summary = resolve_auction_price(
        base.lots,
        html_data=html_data,
        pdf_lots=pdf_lots,
    )
    base.price_parse_status = price_status
    base.price_summary = price_summary
    base.emd_summary = build_emd_summary(emd_status, emd_amount, base.lots)
    base.tax_summary = build_tax_summary(base.lots)
    base.warnings = warnings
    base.missing_fields = compute_missing_fields(base)
    base.parse_confidence = compute_parse_confidence(base)
    base.search_text = build_search_text(base)
    base = apply_display_enrichment(base)
    display_bits = build_display_search_text(base)
    if display_bits:
        base.search_text = f"{base.search_text} {display_bits}".strip()
    base.status = status
    base.errors = errors
    return base


def refresh_auction_emd_fields(record: AuctionRecord) -> AuctionRecord:
    """Recompute EMD status/summary/missing_fields from stored auction fields."""
    html_data = {
        "pre_bid_emd_type": record.pre_bid_emd_type,
        "pre_bid_emd_amount": record.pre_bid_emd_amount,
        "pre_bid_emd_required": record.pre_bid_emd_required,
        "emd_parse_status": record.emd_parse_status,
    }
    emd_type, emd_amount, emd_required, emd_status = resolve_auction_emd(
        html_data=html_data,
        pdf_header=None,
        lots=record.lots,
    )
    updated = record.model_copy(
        update={
            "pre_bid_emd_type": emd_type,
            "pre_bid_emd_amount": emd_amount,
            "pre_bid_emd_required": emd_required,
            "emd_parse_status": emd_status,
            "emd_summary": build_emd_summary(emd_status, emd_amount, record.lots),
        }
    )
    updated.missing_fields = compute_missing_fields(updated)
    updated.parse_confidence = compute_parse_confidence(updated)
    return updated
