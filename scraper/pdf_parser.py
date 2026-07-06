from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber
import pypdf

from scraper.emd import classify_emd_type_text, format_inr_amount, parse_emd_amount
from scraper.price import detect_price_signal

logger = logging.getLogger(__name__)

PDFPLUMBER_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
}

LOT_TABLE_COLUMN_NAMES = (
    "lot details",
    "lot description",
    "lot parameters",
    "other details",
    "lot documents",
)

LOT_TABLE_COLUMN_MAP = {
    "lot details": "lot_details_text",
    "lot description": "lot_description_text",
    "lot parameters": "lot_parameters_text",
    "other details": "lot_other_details_text",
    "lot documents": "lot_documents_text",
}

LOT_SECTION_END_RE = re.compile(
    r"(?:^|\n)(?:"
    + "|".join(re.escape(m) for m in (
        "Terms and Conditions",
        "Special Terms",
        "Inspection Details",
        "Post Auction Payment",
        "Delivery Details",
    ))
    + r")",
    re.I | re.M,
)

VALID_LOT_BLOCK_RE = re.compile(
    r"Lot Name\s*-|Product Type\s*-|Start Price|Quantity\s*-",
    re.I,
)

PARAMETERS_START_RE = re.compile(r"(?:^|\n)Quantity\s*-", re.I | re.M)
DOCUMENTS_START_RE = re.compile(
    r"(?:^|\n)(?:No document\s+Uploaded|Photo for Lot no|Annexure for Lot no)",
    re.I | re.M,
)

DETAIL_FIELD_RE = re.compile(
    r"(?:^|\n)(Lot No|Lot Name|Product Type|Category|PCB Group)\s*-",
    re.I | re.M,
)

FIELD_LINE_PATTERNS = [
    (r"Start Price in INR\s*-\s*\n\s*([\d,.]+)", r"Start Price in INR - \1"),
    (r"Start Price in PER\s*-\s*\n\s*([\d,.]+)", r"Start Price in PER - \1"),
    (r"Bid Increment in INR\s*-\s*\n\s*([\d,.]+)", r"Bid Increment in INR - \1"),
    (r"Increment Price:\s*\n\s*([\d,.]+)", r"Increment Price: \1"),
    (r"Post Bid EMD %\s*-\s*\n\s*([\d,.]+)", r"Post Bid EMD % - \1"),
    (r"TCS \(%\)\s*-\s*\n\s*([\d,.%]+)", r"TCS (%) - \1"),
    (r"GST \(%\)\s*-\s*\n\s*([\d,.%]+|As Applicable)", r"GST (%) - \1"),
    (r"Pre-Bid EMD Amount\s*-\s*\n\s*(.+)", r"Pre-Bid EMD Amount - \1"),
    (r"Pre-Bid EMD Amount\s*:\s*\n\s*([\d,.]+)", r"Pre-Bid EMD Amount: \1"),
    (r"Pre-Bid EMD\s*:\s*\n\s*(.+?)(?=\n)", r"Pre-Bid EMD: \1"),
    (r"Pre Bid EMD\s*:\s*\n\s*(.+?)(?=\n)", r"Pre Bid EMD: \1"),
    (r"Quantity\s*-\s*\n\s*([\d,.]+)", r"Quantity - \1"),
    (r"Lot No\s*-\s*\n\s*(\S+)", r"Lot No - \1"),
    (r"Lot Name\s*-\s*\n\s*(.+?)(?=\nProduct Type)", r"Lot Name - \1"),
]


def extract_pdf_text(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _normalize_field_wrapping(text: str) -> str:
    for pattern, repl in FIELD_LINE_PATTERNS:
        text = re.sub(pattern, repl, text, flags=re.I | re.S)
    text = re.sub(
        r"(Start Price in INR\s*-\s*)(\d)\s*\n\s*(\d)",
        lambda m: m.group(1) + m.group(2) + m.group(3),
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(Bid Increment in INR\s*-\s*)(\d)\s*\n\s*(\d)",
        lambda m: m.group(1) + m.group(2) + m.group(3),
        text,
        flags=re.I,
    )
    return text


def extract_lot_catalogue_section(text: str) -> str:
    """Restrict parsing to catalogue body before terms/inspection sections."""
    end_m = LOT_SECTION_END_RE.search(text)
    end = end_m.start() if end_m else len(text)
    slice_text = text[:end]

    for m in re.finditer(r"Lot No\s*-", slice_text, re.I):
        head = slice_text[m.start() : m.start() + 1200]
        if VALID_LOT_BLOCK_RE.search(head):
            return slice_text[m.start() :]
    return slice_text


def _is_valid_lot_block(block: str) -> bool:
    if not re.match(r"Lot No\s*-\s*", block, re.I):
        return False
    return bool(VALID_LOT_BLOCK_RE.search(block))


def split_lot_blocks(text: str) -> list[str]:
    catalogue = extract_lot_catalogue_section(text)
    catalogue = _normalize_field_wrapping(catalogue)
    parts = re.split(r"(?=\bLot No\s*-\s*)", catalogue, flags=re.I)
    blocks: list[str] = []
    for part in parts:
        part = part.strip()
        if not _is_valid_lot_block(part):
            continue
        m = LOT_SECTION_END_RE.search(part)
        if m and m.start() > 0:
            part = part[: m.start()].strip()
        if _is_valid_lot_block(part):
            blocks.append(part)
    return blocks


def _details_section_end(block: str) -> int:
    """End offset of Lot Details fields (before free-form description)."""
    last_end = 0
    for m in DETAIL_FIELD_RE.finditer(block):
        line_end = block.find("\n", m.start())
        if line_end == -1:
            line_end = len(block)
        last_end = max(last_end, line_end)
    if last_end == 0 and block.strip():
        first_nl = block.find("\n")
        last_end = first_nl if first_nl != -1 else len(block)
    return last_end


def extract_lot_sections(block: str) -> dict[str, str]:
    """Split a lot block into four MSTC catalogue sections."""
    block = _normalize_field_wrapping(block.strip())
    details_end = _details_section_end(block)

    qty_m = PARAMETERS_START_RE.search(block)
    doc_m = DOCUMENTS_START_RE.search(block)

    desc_start = details_end
    desc_end = qty_m.start() if qty_m else (doc_m.start() if doc_m else len(block))

    param_start = qty_m.start() if qty_m else desc_end
    param_end = doc_m.start() if doc_m else len(block)

    no_doc_m = re.search(r"No document\s+Uploaded", block, re.I)
    if no_doc_m:
        doc_start = no_doc_m.start()
        if doc_m:
            doc_start = min(doc_start, doc_m.start())
        if not doc_m or doc_start <= doc_m.start():
            param_end = min(param_end, doc_start)
            doc_text = block[doc_start:].strip()
            doc_text = re.sub(r"No document\s+Uploaded", "No document Uploaded", doc_text, flags=re.I)
        else:
            doc_text = block[doc_m.start() :].strip()
    elif doc_m:
        doc_text = block[doc_m.start() :].strip()
    else:
        tail = block[param_start:]
        tail_doc = re.search(
            r"(?:No document\s+Uploaded|Photo for Lot no|Annexure for Lot no|Annex_|Photo_).+",
            tail,
            re.I | re.S,
        )
        if tail_doc:
            doc_text = tail_doc.group(0).strip()
            doc_text = re.sub(r"No document\s+Uploaded", "No document Uploaded", doc_text, flags=re.I)
            param_end = param_start + tail_doc.start()
        else:
            doc_text = ""

    return {
        "lot_details_text": block[:details_end].strip(),
        "lot_description_text": block[desc_start:desc_end].strip(),
        "lot_parameters_text": block[param_start:param_end].strip(),
        "lot_other_details_text": "",
        "lot_documents_text": doc_text,
    }


def _field_in_cell(cell: str, label: str, following_labels: list[str] | None = None) -> str | None:
    if not cell:
        return None
    if following_labels:
        stops = "|".join(
            rf"(?:^|\n){re.escape(next_label)}\s*-" for next_label in following_labels
        )
        pattern = rf"{re.escape(label)}\s*-\s*(.+?)(?={stops}|\Z)"
    else:
        pattern = rf"{re.escape(label)}\s*-\s*(.+)\Z"
    m = re.search(pattern, cell.strip(), re.I | re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip() or None


def _field_end_of_cell(cell: str, label: str) -> str | None:
    return _field_in_cell(cell, label)


def _field(block: str, label: str, stop_labels: str | None = None) -> str | None:
    if stop_labels:
        pattern = rf"{re.escape(label)}\s*-\s*(.+?)(?={stop_labels})"
    else:
        pattern = rf"{re.escape(label)}\s*-\s*(.+?)(?:\n[A-Z][^\n]{{0,40}}\s*-|\Z)"
    m = re.search(pattern, block, re.S | re.I)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip() or None


def _parse_price_inr(raw: str | None) -> int | None:
    amount = parse_emd_amount(raw)
    if amount is None:
        return None
    return int(amount)


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"([\d.]+)", raw.replace(",", ""))
    return float(m.group(1)) if m else None


def _norm_lot_no(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _clean_description_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def compute_lot_parse_warnings(lot: dict) -> list[str]:
    warnings: list[str] = []
    if not (lot.get("lot_details_text") or "").strip():
        warnings.append("missing_lot_details_text")
    if not (lot.get("lot_description_text") or "").strip():
        warnings.append("missing_lot_description_text")
    if not (lot.get("lot_parameters_text") or "").strip():
        warnings.append("missing_lot_parameters_text")
    if not (lot.get("lot_other_details_text") or "").strip():
        warnings.append("missing_lot_other_details_text")
    if not (lot.get("lot_documents_text") or "").strip():
        warnings.append("missing_lot_documents_text")
    if not lot.get("lot_no"):
        warnings.append("missing_lot_no")
    if not (lot.get("lot_name") or "").strip():
        warnings.append("missing_item_title")
    if lot.get("start_price") is None and not lot.get("start_price_text"):
        warnings.append("missing_price_parameter")
    return warnings


def _cell_text(cell: object) -> str:
    if cell is None:
        return ""
    return str(cell).replace("\r\n", "\n").strip()


def _normalize_column_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace(":", "")).strip().lower()


def _match_lot_table_columns(row: list[object] | None) -> dict[str, int] | None:
    if not row:
        return None
    normalized = [_normalize_column_name(_cell_text(c)) for c in row]
    indices: dict[str, int] = {}
    for col_name in LOT_TABLE_COLUMN_NAMES:
        try:
            indices[col_name] = normalized.index(col_name)
        except ValueError:
            return None
    return {LOT_TABLE_COLUMN_MAP[name]: indices[name] for name in LOT_TABLE_COLUMN_NAMES}


def _row_is_lot_data(row: list[object], col_map: dict[str, int]) -> bool:
    idx = col_map.get("lot_details_text")
    if idx is None or idx >= len(row):
        return False
    details = _cell_text(row[idx])
    return bool(re.search(r"Lot No\s*-", details, re.I))


def _sections_from_table_row(row: list[object], col_map: dict[str, int]) -> dict[str, str]:
    sections: dict[str, str] = {}
    for field, idx in col_map.items():
        sections[field] = _cell_text(row[idx]) if idx < len(row) else ""
    return sections


def _split_other_details_from_parameters(sections: dict[str, str]) -> dict[str, str]:
    params = sections.get("lot_parameters_text", "") or ""
    if sections.get("lot_other_details_text", "").strip():
        return sections
    other_start = re.search(
        r"(?:^|\n)(?:GST \(%\)|Lot Location\s*-|Lot State\s*-|Bid Valid Till\s*-)",
        params,
        re.I | re.M,
    )
    if other_start:
        sections = dict(sections)
        sections["lot_other_details_text"] = params[other_start.start() :].strip()
        sections["lot_parameters_text"] = params[: other_start.start()].strip()
    return sections


def extract_lots_from_pdfplumber(pdf_path: Path) -> list[dict]:
    lots: list[dict] = []
    col_map: dict[str, int] | None = None

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(PDFPLUMBER_TABLE_SETTINGS) or []
            for table in tables:
                if not table:
                    continue

                start_row = 0
                if col_map is None:
                    for i, row in enumerate(table):
                        matched = _match_lot_table_columns(row)
                        if matched:
                            col_map = matched
                            start_row = i + 1
                            break
                if col_map is None:
                    continue

                for row in table[start_row:]:
                    if not row:
                        continue
                    header_match = _match_lot_table_columns(row)
                    if header_match:
                        col_map = header_match
                        continue
                    if not _row_is_lot_data(row, col_map):
                        continue
                    sections = _sections_from_table_row(row, col_map)
                    lots.append(parse_lot_from_sections(sections))

    return lots


def parse_lot_from_sections(sections: dict[str, str]) -> dict:
    sections = _split_other_details_from_parameters(sections)
    details = sections.get("lot_details_text", "") or ""
    description = sections.get("lot_description_text", "") or ""
    parameters = sections.get("lot_parameters_text", "") or ""
    other = sections.get("lot_other_details_text", "") or ""
    documents = sections.get("lot_documents_text", "") or ""

    block_norm = _normalize_field_wrapping(
        "\n".join(part for part in (details, description, parameters, other, documents) if part)
    )

    lot_no_raw = _field(details, "Lot No") or _field(block_norm, "Lot No")
    lot_no = _norm_lot_no(lot_no_raw) if lot_no_raw else ""

    lot_name = _field(details, "Lot Name", stop_labels=r"\nProduct Type") or _field(
        block_norm, "Lot Name", stop_labels=r"\nProduct Type"
    )
    product_type = _field_in_cell(details, "Product Type", ["Category", "PCB Group"]) or _field(
        details, "Product Type", stop_labels=r"\nCategory"
    ) or _field(block_norm, "Product Type", stop_labels=r"\nCategory")
    category = _field_in_cell(details, "Category", ["PCB Group"]) or _field(
        details, "Category", stop_labels=r"\nPCB Group|\nQuantity|\nBEML|\nNote"
    ) or _field(block_norm, "Category", stop_labels=r"\nPCB Group|\nQuantity|\nBEML|\nNote")
    pcb_group = _field_end_of_cell(details, "PCB Group") or _field(
        details, "PCB Group", stop_labels=r"\nQuantity|\nBEML|\nNote"
    ) or _field(block_norm, "PCB Group", stop_labels=r"\nQuantity|\nBEML|\nNote")
    quantity_raw = _field(parameters, "Quantity", stop_labels=r"\nUnit|\nStart Price|\nBEML|\nNote")
    if not quantity_raw:
        quantity_raw = _field(block_norm, "Quantity", stop_labels=r"\nUnit|\nStart Price|\nBEML|\nNote")
    unit = _field(parameters, "Unit", stop_labels=r"\nStart Price|\nBEML|\nNote") or _field(
        block_norm, "Unit", stop_labels=r"\nStart Price|\nBEML|\nNote"
    )

    start_price = None
    start_price_label = None
    start_price_text = None
    price_m = re.search(r"Start Price in INR\s*-\s*([\d,]+)", parameters or block_norm, re.I)
    if price_m:
        start_price = _parse_price_inr(price_m.group(1))
        start_price_label = (
            format_inr_amount(start_price)
            if start_price and start_price > 1
            else "Floor price ₹1 (open bidding)"
        )
    else:
        per_m = re.search(r"Start Price in PER\s*-\s*([\d,.]+)", parameters or block_norm, re.I)
        if per_m:
            pct = per_m.group(1).strip()
            start_price_text = f"Premium {pct}%"
        else:
            alt = re.search(
                r"Start Price is\s*:\s*INR\s*([\d,]+)\s*/-\s*per\s*(\w+)",
                block_norm,
                re.I,
            )
            if alt:
                start_price = _parse_price_inr(alt.group(1))
                start_price_text = f"INR {alt.group(1)} /- per {alt.group(2)}"
                start_price_label = start_price_text
            else:
                pct = re.search(
                    r"(bidding to be done in percentage.+?)(?:\n|$)",
                    block_norm,
                    re.I,
                )
                if pct:
                    start_price_text = re.sub(r"\s+", " ", pct.group(1)).strip()
                elif detect_price_signal(block_norm):
                    for line in block_norm.splitlines():
                        if detect_price_signal(line):
                            start_price_text = re.sub(r"\s+", " ", line).strip()
                            break

    bid_increment = _parse_float(_field(parameters, "Bid Increment in INR"))
    if bid_increment is None:
        bid_increment = _parse_float(_field(block_norm, "Bid Increment in INR"))
    if bid_increment is None:
        inc_m = re.search(r"Increment Price:\s*([\d,.]+)", block_norm, re.I)
        if inc_m:
            bid_increment = _parse_float(inc_m.group(1))

    post_bid_emd_percent = _parse_float(_field(parameters, "Post Bid EMD %"))
    if post_bid_emd_percent is None:
        post_bid_emd_percent = _parse_float(_field(block_norm, "Post Bid EMD %"))
    tcs_percent = _parse_float(_field(parameters, "TCS (%)"))
    if tcs_percent is None:
        tcs_percent = _parse_float(_field(block_norm, "TCS (%)"))

    gst_raw = _field(other, "GST (%)") or _field(parameters, "GST (%)") or _field(block_norm, "GST (%)")
    gst_percent = (
        _parse_float(gst_raw) if gst_raw and "applicable" not in gst_raw.lower() else None
    )
    gst_text = gst_raw

    lot_location = (
        _field(other, "Lot Location", stop_labels=r"\nLot State|\nState\s*:")
        or _field(block_norm, "Lot Location", stop_labels=r"\nLot State|\nState\s*:")
    )
    lot_state = (
        _field(other, "Lot State", stop_labels=r"\nBid Valid|\nPre-Bid|\nPhoto|\nAnnexure")
        or _field(block_norm, "Lot State", stop_labels=r"\nBid Valid|\nPre-Bid|\nPhoto|\nAnnexure")
    )
    if not lot_state and lot_location:
        state_m = re.search(r"State\s*:\s*([^\n]+)", lot_location, re.I)
        if state_m:
            lot_state = state_m.group(1).strip()

    bid_valid_till = (
        _field(other, "Bid Valid Till", stop_labels=r"\nPre-Bid|\nPhoto|\nAnnexure")
        or _field(block_norm, "Bid Valid Till", stop_labels=r"\nPre-Bid|\nPhoto|\nAnnexure")
    )

    pre_bid_emd_amount = None
    pre_bid_emd_text = None
    emd_m = re.search(r"Pre-Bid EMD Amount\s*-\s*(.+?)(?:\n|$)", block_norm, re.I)
    if emd_m:
        raw_emd = emd_m.group(1).strip()
        pre_bid_emd_amount = parse_emd_amount(raw_emd)
        if pre_bid_emd_amount is None and raw_emd:
            pre_bid_emd_text = raw_emd
    else:
        emd_colon = re.search(r"Pre-Bid EMD Amount\s*:\s*(.+?)(?:\n|$)", block_norm, re.I)
        if emd_colon:
            raw_emd = emd_colon.group(1).strip()
            pre_bid_emd_amount = parse_emd_amount(raw_emd)
            if pre_bid_emd_amount is None and raw_emd:
                pre_bid_emd_text = raw_emd
        else:
            emd_alt = re.search(
                r"Pre Bid EMD\s*:\s*(INR\s*.+?)(?:\n|$)",
                block_norm,
                re.I,
            )
            if emd_alt:
                pre_bid_emd_text = emd_alt.group(1).strip()
                pre_bid_emd_amount = parse_emd_amount(pre_bid_emd_text)

    annexure_file = None
    photo_file = None
    doc_text = documents or block_norm
    annex_m = re.search(
        r"Annexure for Lot\s*no\s*\d+\s*-\s*(.+?)(?:\nPhoto for Lot|\nNo document|\Z)",
        doc_text,
        re.I | re.S,
    )
    if annex_m:
        annexure_file = re.sub(r"\s+", "", annex_m.group(1)).strip()
    photo_m = re.search(
        r"Photo for Lot\s*no\s*\d+\s*-\s*(.+?)(?:\nAnnexure for Lot|\nNo document|\Z)",
        doc_text,
        re.I | re.S,
    )
    if photo_m:
        photo_file = re.sub(r"\s+", "", photo_m.group(1)).strip()

    quantity = quantity_raw
    if quantity_raw and unit and unit not in quantity_raw:
        quantity = f"{quantity_raw} {unit}".strip()

    item_description = _clean_description_text(description)

    result = {
        "lot_no": lot_no,
        "lot_name": lot_name or lot_no,
        "item_description": item_description,
        "product_type": product_type,
        "category": category,
        "pcb_group": pcb_group,
        "quantity": quantity,
        "unit": unit,
        "start_price": start_price,
        "start_price_label": start_price_label,
        "start_price_text": start_price_text,
        "bid_increment": bid_increment,
        "post_bid_emd_percent": post_bid_emd_percent,
        "tcs_percent": tcs_percent,
        "gst_percent": gst_percent,
        "gst_text": gst_text,
        "lot_location": lot_location,
        "lot_state": lot_state,
        "bid_valid_till": bid_valid_till,
        "pre_bid_emd_amount": pre_bid_emd_amount,
        "pre_bid_emd_text": pre_bid_emd_text,
        "annexure_file": annexure_file,
        "photo_file": photo_file,
        **sections,
    }
    result["lot_parse_warnings"] = compute_lot_parse_warnings(result)
    return result


def parse_lot_block(block: str) -> dict:
    sections = extract_lot_sections(block)
    return parse_lot_from_sections(sections)


def parse_pdf_lots(pdf_path: Path) -> list[dict]:
    try:
        lots = extract_lots_from_pdfplumber(pdf_path)
        if lots:
            logger.info("Parsed %d lots from %s via pdfplumber tables", len(lots), pdf_path.name)
            return lots
    except Exception as exc:
        logger.warning("pdfplumber table extraction failed for %s: %s", pdf_path.name, exc)

    text = extract_pdf_text(pdf_path)
    blocks = split_lot_blocks(text)
    lots = [parse_lot_block(b) for b in blocks]
    logger.info("Parsed %d lots from %s via pypdf blocks", len(lots), pdf_path.name)
    return lots


def _parse_pdf_emd_header(header: str) -> dict:
    header = _normalize_field_wrapping(header)
    emd_type_raw = None
    emd_type_m = re.search(
        r"Pre-Bid EMD\s*:\s*(.+?)(?:\n|Pre-Bid EMD Amount|$)", header, re.I | re.S
    )
    if emd_type_m:
        emd_type_raw = re.sub(r"\s+", " ", emd_type_m.group(1)).strip()

    emd_amount = None
    for pattern in (
        r"Pre-Bid EMD Amount\s*-\s*(.+?)(?:\n|$)",
        r"Pre-Bid EMD Amount\s*:\s*(.+?)(?:\n|$)",
    ):
        amount_m = re.search(pattern, header, re.I)
        if amount_m:
            emd_amount = parse_emd_amount(amount_m.group(1).strip())
            if emd_amount is not None:
                break

    emd_required, emd_status = classify_emd_type_text(emd_type_raw)
    return {
        "pre_bid_emd_type": emd_type_raw,
        "pre_bid_emd_amount": emd_amount,
        "pre_bid_emd_required": emd_required,
        "emd_parse_status": emd_status,
    }


def parse_pdf_header(pdf_path: Path) -> dict:
    text = extract_pdf_text(pdf_path)
    header = text[:5000]
    emd = _parse_pdf_emd_header(header)
    return {
        "auction_number": _field(header, "Auction No") or _field(header, "Auction Number"),
        "seller": _field(header, "Seller Name") or _field(header, "Seller"),
        "location": _field(header, "Location"),
        "opening": _field(header, "Opening Date"),
        "closing": _field(header, "Closing Date"),
        **emd,
    }
