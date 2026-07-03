"""Hand-crafted archive catalog for auction 33637 (CTS/3211/DISP/26-27/04/Scrap)."""

from __future__ import annotations

from typing import Any

_LOC_OLD = "MO(V) / OLD SITE, Visakhapatnam"
_CONTACT_OLD = "0891-2815089 / 5095"
_CPCB = "CPCB / MOEF / State PCB certificate mandatory (Lot 3A)"


def _evidence(page: int, excerpt: str) -> dict[str, Any]:
    return {
        "source": "tender_pdf",
        "page_no": page,
        "page_image": f"images/page-{page:02d}.png",
        "ocr_excerpt": excerpt,
    }


def _item(
    sub_code: str,
    title: str,
    plain: str,
    quantity: float | int,
    unit: str,
    tags: list[str],
    page: int,
    excerpt: str,
) -> dict[str, Any]:
    return {
        "sub_code": sub_code,
        "title": title,
        "description_verbatim": title,
        "plain_language": plain,
        "quantity": quantity,
        "unit": unit,
        "material_tags": tags,
        "evidence": _evidence(page, excerpt),
    }


ARCHIVE_33637: list[dict[str, Any]] = [
    {
        "lot_code": "1A",
        "lot_summary_plain": (
            "**Lot 1A** at MO(V) Old Site combines **heavy melt scrap** with **furniture and plant**. "
            "Key weights: **40 MT machinery scrap** and **150 MT iron scrap**, plus gas cylinders, "
            "**200 chairs**, seven engines, and twelve hand trolleys. Pre-bid EMD **₹10 lakh**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 1000000,
        "unit_of_sale": "By Lot",
        "document_pages": [2],
        "items": [
            _item("A", "Machinery scrap (40 MT)", "Forty tonnes **machinery and plant metal** for cutting and melting.", 40, "MT", ["machinery_scrap", "hms_iron"], 2, "(A) Machinery Scrap, Qty-40 MT"),
            _item("B", "Iron scrap (150 MT)", "One hundred fifty tonnes **HMS iron/steel scrap**.", 150, "MT", ["hms_iron", "mt_scrap"], 2, "(B) Iron Scrap, Qty-150 MT"),
            _item("C", "Trolley-mounted cylinders (10 nos)", "Ten **75 kg-type gas cylinders on trolleys**.", 10, "Nos", ["gas_cylinder", "industrial_equipment"], 2, "(C) Trolley Mounted Cylinders (75 Kgs) Assorted, Qty-10 Nos."),
            _item("D", "Chairs (200 nos)", "Two hundred **chairs** — office/mess furniture bundled with scrap lot.", 200, "Nos", ["chair", "furniture"], 2, "(D) Chairs Assorted, Qty-200 Nos"),
            _item("E", "Engines (7 nos)", "Seven **engine units** for parts or scrap.", 7, "Nos", ["engine", "industrial_equipment"], 2, "(E) Engines Assorted, Qty-07 Nos"),
            _item("F", "Hand trolleys (12 nos)", "Twelve **manual hand trolleys**.", 12, "Nos", ["hand_trolley", "industrial_equipment"], 2, "(F) Hand Trolley Assorted, Qty-12 Nos."),
        ],
    },
    {
        "lot_code": "2A",
        "lot_summary_plain": (
            "**Lot 2A** is **precision workshop machinery** — rotor balancer (3000 kg), induction regulators, "
            "and a 1-ton shearing/punching machine. **CPCB certificate required.** EMD **₹50,000**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 50000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": _CPCB,
        "document_pages": [2],
        "items": [
            _item("A", "Rotor balancing machine (3000 kg, 1 no)", "One **3000 kg-capacity rotor balancing machine**.", 1, "No", ["balancing_machine", "industrial_equipment"], 2, "(A) Rotor Balancing Machine Assorted (3000 Kg Capacity), Qty-01 No."),
            _item("B", "Induction regulator set (1100 kg, 2 nos)", "Two **induction regulator units** (~1100 kg capacity each).", 2, "Nos", ["induction_regulator", "industrial_equipment"], 2, "(B) Induction Regulator (Complete Set) Assorted (1100 Kgs Capacity), Qty-02 Nos."),
            _item("C", "Shearing/punching machine (1 ton, 1 no)", "One **1-ton vertical shearing and punching machine**.", 1, "No", ["sheet_metal_machine", "industrial_equipment"], 2, "(C) Vertical Universal Sharing Punching, Cropping & Machine Assorted (01 Ton Capacity), Qty-01 No."),
        ],
    },
    {
        "lot_code": "3A",
        "lot_summary_plain": (
            "**Lot 3A** is the **main value lot**: **239 submarine batteries** and **2000 mattresses**. "
            "Batteries are very heavy, regulated hazardous waste. Only **CPCB-licensed** bidders. EMD **₹40 lakh**. "
            "H1 was **accepted** at ₹1.64 Cr (Southern Power Industries)."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 4000000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": _CPCB,
        "document_pages": [2],
        "items": [
            _item(
                "A", "Submarine batteries (239 nos)",
                "Two hundred thirty-nine **submarine/ship battery cells** — large lead-acid banks requiring "
                "licensed transport and recycling.",
                239, "Nos", ["lead_acid_battery", "submarine_battery"], 2,
                "(A) Submarine Batteries, Qty-239 Nos",
            ),
            _item("B", "Foam / coir mattresses (2000 nos)", "Two thousand **mattresses** sold with the battery lot.", 2000, "Nos", ["mattress", "foam_mattress"], 2, "(B) Foam / Coir Mattress Assorted, Qty -2000 Nos"),
        ],
    },
    {
        "lot_code": "4A",
        "lot_summary_plain": (
            "**Lot 4A** is **200 assorted tyres** at MO(V) Old Site, sold **by count**. "
            "Listed in the tender and on GeM with opening price, but **no winning bid recorded** in the published result."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 100000,
        "unit_of_sale": "By Count",
        "regulatory_notes": "Tyre disposal — pollution-board norms may apply",
        "document_pages": [2],
        "items": [
            _item("A", "Tyres assorted (200 nos)", "Two hundred **used tyres** — retreading, crumb rubber, or licensed disposal.", 200, "Nos", ["tyres", "tyre"], 2, "Tyres Assorted, Qty-200 Nos"),
        ],
    },
    {
        "lot_code": "5A",
        "lot_summary_plain": (
            "**Lot 5A** spans Naval Dockyard: **15/3-ton EOT crane** at ND(V)/MSAX and "
            "**12,000 empty H₂SO₄ glass bottles** at ND(V)/MECE. EMD **₹50,000**."
        ),
        "location": "ND(V)/ MSAX & ND(V)/ MECE, Visakhapatnam",
        "contact": "MSAX: Mr. RT Moorthi 9246156575; MECE: Mr. Hari 9948062747",
        "pre_bid_emd_inr": 50000,
        "unit_of_sale": "By Lot",
        "document_pages": [2],
        "items": [
            _item("A", "EOT crane 15/3 ton (1 no)", "One **15/3-tonne EOT crane** — Survey No. 20252368P0004.", 1, "No", ["crane", "eot_crane", "industrial_equipment"], 2, "(A) EOT Crane (15/3 Ton) Assorted,Qty-01 No."),
            _item("B", "H₂SO₄ empty glass bottles (12,000 nos)", "Twelve thousand **empty acid glass bottles** — lab waste.", 12000, "Nos", ["glass_bottle", "lab_waste"], 2, "(B) H2SO04 Empty Glass Bottles, Qty-12000 Nos."),
        ],
    },
    {
        "lot_code": "6A",
        "lot_summary_plain": (
            "**Lot 6A** is a **small Hyderabad liaison-office lot** — IT scrap, cameras, printers, and minor metals. "
            "Listed on GeM but **no H1 result published**."
        ),
        "location": "Naval Liaison Cell, Hyderabad",
        "contact": "Cdr Satish, PH: 9427968639",
        "pre_bid_emd_inr": 5000,
        "unit_of_sale": "By Lot",
        "document_pages": [3],
        "items": [
            _item("A", "W/T electrical scrap (65.5 kg)", "UPS units, RAM, motherboards, and telecom e-waste.", 65.5, "Kgs", ["electrical_scrap", "wt_electrical", "mixed_ewaste"], 3, "(A) W/T Electrical Scrap, Qty-65.5 Kgs"),
            _item("B", "Camera (1 no)", "One camera.", 1, "No", ["camera", "mixed_ewaste"], 3, "(B) Camera Assorted, Qty-01 No."),
            _item("C", "Vacuum cleaner (1 no)", "One vacuum cleaner.", 1, "No", ["vacuum_cleaner", "mixed_ewaste"], 3, "(C) Vaccum Cleaner Assorted, Qty-01 No."),
            _item("D", "Plastic scrap (7.9 kg)", "Mixed office plastic scrap.", 7.9, "Kgs", ["plastic_scrap", "mixed_ewaste"], 3, "(D) Plastic Scrap, Qty-7.9 Kgs"),
            _item("E", "Iron scrap (18.5 kg)", "Small iron scrap including bicycle frame.", 18.5, "Kgs", ["hms_iron"], 3, "(E) Iron Scrap, Qty-18.5 Kgs"),
            _item("G", "Printers (2 nos)", "Two printers.", 2, "Nos", ["printer", "mixed_ewaste"], 3, "(G) Printer Assorted, Qty-02 Nos"),
            _item("H", "Chairs (17 nos)", "Seventeen chairs.", 17, "Nos", ["chair", "furniture"], 3, "(H) Chairs Assorted, Qty-17 Nos"),
            _item("J", "Tool scrap (600 g)", "Arboriculture tool scrap.", 0.6, "Kgs", ["tool_scrap"], 3, "(J) Tool Scrap, Qty-600 Grms"),
            _item("K", "Personal computers (3 nos)", "Three desktop PCs.", 3, "Nos", ["computer", "mixed_ewaste"], 3, "(K) Personal Computer Assorted, Qty-03 Nos"),
            _item("L", "Xerox machine (1 no)", "One photocopier.", 1, "No", ["xerox", "printer", "mixed_ewaste"], 3, "(L) Xerox Machine Assorted, Qty-01 No."),
        ],
    },
]

LOTS = ARCHIVE_33637

META = {
    "reference_no": "CTS/3211/DISP/26-27/04/Scrap dated 14 May 26",
    "auction_date": "2026-05-14",
    "region": "Visakhapatnam & Hyderabad",
    "location_summary": "MO(V) Old Site; Naval Dockyard MSAX/MECE; Naval Liaison Cell Hyderabad",
}
