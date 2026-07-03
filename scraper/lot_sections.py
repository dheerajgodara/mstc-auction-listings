from __future__ import annotations

from scraper.models import LotRecord


def _has_text(value: str | None) -> bool:
    return bool(value and str(value).strip())


def synthesize_lot_sections(lot: LotRecord) -> LotRecord:
    """Fill missing raw section text from structured fields when PDF extraction failed."""
    details = lot.lot_details_text
    parameters = lot.lot_parameters_text
    other = lot.lot_other_details_text
    documents = lot.lot_documents_text
    description = lot.lot_description_text

    if not _has_text(details):
        lines: list[str] = []
        if lot.lot_id:
            lines.append(f"Lot No - {lot.lot_id}")
        if lot.item_title and lot.item_title != lot.lot_id:
            lines.append(f"Lot Name - {lot.item_title}")
        if lot.product_type:
            lines.append(f"Product Type - {lot.product_type}")
        if lot.category:
            lines.append(f"Category - {lot.category}")
        if lot.pcb_group:
            lines.append(f"PCB Group - {lot.pcb_group}")
        if lines:
            details = "\n".join(lines)

    if not _has_text(description) and _has_text(lot.item_description):
        description = lot.item_description

    if not _has_text(parameters):
        lines = []
        if lot.quantity:
            lines.append(f"Quantity - {lot.quantity}")
        if lot.start_price_text:
            if "PER" in lot.start_price_text.upper() or "%" in lot.start_price_text:
                m = lot.start_price_text.replace("Premium ", "").replace("%", "").strip()
                lines.append(f"Start Price in PER - {m}")
            else:
                lines.append(f"Start Price - {lot.start_price_text}")
        elif lot.start_price is not None:
            lines.append(f"Start Price in INR - {int(lot.start_price)}")
        elif lot.start_price_inr is not None:
            lines.append(f"Start Price in INR - {int(lot.start_price_inr)}")
        if lot.bid_increment is not None:
            lines.append(f"Bid Increment in INR - {lot.bid_increment}")
        if lot.post_bid_emd_percent is not None:
            lines.append(f"Post Bid EMD % - {lot.post_bid_emd_percent}")
        if lot.tcs:
            lines.append(f"TCS (%) - {lot.tcs}")
        if lot.pre_bid_emd_text:
            lines.append(f"Pre-Bid EMD Amount - {lot.pre_bid_emd_text}")
        elif lot.pre_bid_emd_amount is not None:
            lines.append(f"Pre-Bid EMD Amount - {lot.pre_bid_emd_amount}")
        if lines:
            parameters = "\n".join(lines)

    if not _has_text(other):
        lines = []
        if lot.gst:
            lines.append(f"GST (%) - {lot.gst}")
        if lot.location:
            lines.append(f"Lot Location - {lot.location}")
        if lot.lot_state:
            lines.append(f"Lot State - {lot.lot_state}")
        if lot.bid_valid_till:
            lines.append(f"Bid Valid Till - {lot.bid_valid_till}")
        if lines:
            other = "\n".join(lines)

    if not _has_text(documents):
        doc_lines: list[str] = []
        if lot.annexure_file:
            lot_no = lot.lot_id or "1"
            doc_lines.append(f"Annexure for Lot no {lot_no} - {lot.annexure_file}")
        if lot.photo_file:
            lot_no = lot.lot_id or "1"
            doc_lines.append(f"Photo for Lot no {lot_no} - {lot.photo_file}")
        if doc_lines:
            documents = "\n".join(doc_lines)

    return lot.model_copy(
        update={
            "lot_details_text": details,
            "lot_description_text": description,
            "lot_parameters_text": parameters,
            "lot_other_details_text": other,
            "lot_documents_text": documents,
        }
    )
