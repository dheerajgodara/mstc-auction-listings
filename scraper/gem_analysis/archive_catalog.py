from __future__ import annotations

from typing import Any

_LOC = "MO(V) / OLD SITE, Visakhapatnam"
_CONTACT = "0891-2815089 / 5095"


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
    quantity_notes: str | None = None,
) -> dict[str, Any]:
    return {
        "sub_code": sub_code,
        "title": title,
        "description_verbatim": title,
        "plain_language": plain,
        "quantity": quantity,
        "unit": unit,
        "quantity_notes": quantity_notes,
        "material_tags": tags,
        "evidence": _evidence(page, excerpt),
    }


ARCHIVE_31705: list[dict[str, Any]] = [
    {
        "lot_code": "1A",
        "lot_summary_plain": (
            "This lot is a **material-handling and rope-scrap bundle** from the Indian Navy Material Organisation "
            "depot at Visakhapatnam (Old Site). In plain terms: you are buying used trolleys and fork-lifts that moved "
            "stores around the yard, plus a large pile of old plastic (polypropylene) rope and steel wire rope sold as scrap. "
            "All items are sold together — you cannot pick individual pieces. Inspection was allowed on 10–11 Mar 2026. "
            "Only bidders with a valid **CPCB / pollution-board certificate** may participate."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 100000,
        "unit_of_sale": "By Lot (entire lot must be taken)",
        "regulatory_notes": "CPCB / MOEF / State PCB certificate mandatory",
        "document_pages": [2],
        "items": [
            _item(
                "A", "Hand trolleys (5 units)",
                "Five ordinary **hand-pushed platform trolleys** — the type used to move boxes and stores by hand "
                "inside warehouses. Condition is “as is”; may be rusted or incomplete.",
                5, "Nos", ["hand_trolley", "industrial_equipment"], 2,
                "(A) Hand Trolley Assorted, Qty-05 Nos",
            ),
            _item(
                "B", "Fork-lift trucks (11 units)",
                "Eleven **fork-lift / fork-lifter machines** — motorised vehicles with forks for lifting pallets and heavy "
                "loads. These are full machines, not just scrap metal. Useful for resale as equipment or breaking for parts.",
                11, "Nos", ["fork_lifter", "industrial_equipment"], 2,
                "(B) Fork Lifters Assorted, Qty-11 Nos",
            ),
            _item(
                "C", "Battery-operated trolleys (32 units)",
                "Thirty-two **battery-powered platform trolleys** — electric carts for moving goods over short distances "
                "without manual pushing. Batteries and chargers may or may not be included; condition not guaranteed.",
                32, "Nos", ["battery_trolley", "industrial_equipment"], 2,
                "(C) Battery Operated Trolley Assorted, Qty-32 Nos",
            ),
            _item(
                "D", "Polypropylene rope scrap (30 tonnes)",
                "Thirty **metric tonnes** of used **polypropylene (plastic) rope** in mixed thicknesses — 24 mm, 32 mm, "
                "48 mm, 64 mm and similar. This is naval mooring/utility rope past useful life, sold as plastic scrap "
                "for recycling, not as reusable rope.",
                30, "MT", ["polypropylene_rope", "rope_scrap"], 2,
                "Polypropylene Rope ... Scrap, Qty- 30 MT",
            ),
            _item(
                "E", "Steel wire rope scrap (3 tonnes)",
                "Three **metric tonnes** of old **steel wire rope** (cable) — typically used on ships and cranes. "
                "Sold as ferrous scrap for melting; may contain grease and fittings.",
                3, "MT", ["steel_wire_rope", "wire_rope"], 2,
                "Steel Wire Rope Assorted, Qty- 03 MT",
            ),
        ],
    },
    {
        "lot_code": "2A",
        "lot_summary_plain": (
            "This is the **largest mixed electronics lot** in the auction — essentially a full **office + appliances "
            "clearance** from the same naval depot. It includes **700 computers**, **500 televisions**, hundreds of "
            "printers, ACs, fridges, fans, and roughly **1,000 mattresses**. Think of it as an entire establishment’s "
            "IT equipment, consumer appliances, and furnishings being sold in one go. "
            "Because it contains e-waste, only **CPCB-authorised recyclers** can bid. Everything is “as is where is” — "
            "working and non-working items mixed together."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 100000,
        "unit_of_sale": "By Lot (entire lot must be taken)",
        "regulatory_notes": "CPCB / MOEF / State PCB certificate mandatory (e-waste lot)",
        "document_pages": [2],
        "items": [
            _item("A", "Projectors (15)", "Fifteen **data/video projectors** — meeting-room and training equipment, likely mixed brands and condition.", 15, "Nos", ["projector", "mixed_ewaste", "ewaste"], 2, "(A) Projectors Assorted, Qty-15 Nos"),
            _item("B", "Laptops (11)", "Eleven **laptop computers** — assorted makes; may be dead, damaged, or partially working.", 11, "Nos", ["laptop", "mixed_ewaste"], 2, "Laptops Assorted, Qty-11 Nos"),
            _item("C", "Binoculars (135)", "One hundred thirty-five **binoculars** — optical equipment, possibly naval/survey type; sold as bulk lot.", 135, "Nos", ["binocular", "mixed_ewaste"], 2, "Binoculars Assorted, Qty-135 Nos"),
            _item("D", "Televisions (500)", "Five hundred **TV sets** — the single largest line item by count. Mixed LCD/LED types; typical office/barracks disposal.", 500, "Nos", ["television", "mixed_ewaste"], 2, "Television Assorted, Qty-500 Nos"),
            _item("E", "Cameras (15)", "Fifteen **still/video cameras** — assorted; may include DSLR or compact types.", 15, "Nos", ["camera", "mixed_ewaste"], 2, "Camera Assorted, Qty-15 Nos"),
            _item("F", "CCTV cameras (20)", "Twenty **CCTV / surveillance cameras** — security equipment with wiring housings.", 20, "Nos", ["cctv", "camera", "mixed_ewaste"], 2, "CCTV Camera Assorted, Qty-20 Nos"),
            _item("G", "Thermal cameras (6)", "Six **thermal imaging cameras** — specialised night/heat vision equipment; higher value per unit.", 6, "Nos", ["camera", "mixed_ewaste"], 2, "Thermal imaging Camera Assorted, Qty-06 Nos"),
            _item("H", "Water purifiers (150)", "One hundred fifty **water purifiers / RO units** — office and domestic type.", 150, "Nos", ["water_purifier", "mixed_ewaste"], 2, "Water Purifier Assorted, Qty- 150 Nos"),
            _item("J", "Computers / all-in-one PCs (700)", "Seven hundred **desktop computers and all-in-one PCs** — the core IT disposal. CPUs, monitors combined or separate; huge bulk for e-waste processing or refurbishment.", 700, "Nos", ["computer", "mixed_ewaste"], 2, "Computers / All in One ... Qty-700 Nos"),
            _item("K", "Printers (100)", "One hundred **printers** — inkjet/laser office printers.", 100, "Nos", ["printer", "mixed_ewaste"], 2, "Printers Assorted, Qty-100 Nos"),
            _item("L", "Photocopiers / Xerox (50)", "Fifty **photocopy machines (Xerox-type)** — heavier office machines than ordinary printers.", 50, "Nos", ["xerox", "printer", "mixed_ewaste"], 2, "Xerox Machine Assorted, Qty-50 Nos"),
            _item("M", "Air conditioners (50)", "Fifty **air-conditioning units** — split/window types; gas and compressors may need licensed handling.", 50, "Nos", ["air_conditioner", "mixed_ewaste"], 2, "Air Conditioners Assorted, Qty-50 Nos"),
            _item("N", "Refrigerators (30)", "Thirty **refrigerators** — domestic/commercial cooling units.", 30, "Nos", ["refrigerator", "mixed_ewaste"], 2, "Refrigerators Assorted, Qty-30 Nos"),
            _item("P", "Washing machines (20)", "Twenty **washing machines**.", 20, "Nos", ["washing_machine", "mixed_ewaste"], 2, "Washing Machines Assorted, Qty-20 Nos"),
            _item("Q", "Microwave ovens (25)", "Twenty-five **microwave ovens**.", 25, "Nos", ["microwave", "mixed_ewaste"], 2, "Micro Ovens Assorted, Qty-25 Nos"),
            _item("R", "Geysers / water heaters (10)", "Ten **electric geysers (water heaters)**.", 10, "Nos", ["geyser", "mixed_ewaste"], 2, "Geysers Assorted, Qty-10 Nos"),
            _item("S", "Generators (8)", "Eight **portable generators** — diesel/petrol sets for backup power.", 8, "Nos", ["generator", "mixed_ewaste"], 2, "Generators Assorted, Qty-08 Nos"),
            _item("T", "Sextants (6)", "Six **sextants** — nautical navigation instruments (brass/optical).", 6, "Nos", ["sextant", "mixed_ewaste"], 2, "Sextant Assorted, Qty-06 Nos"),
            _item("U", "Bearing sets / sites (14)", "Fourteen **bearing-related items** (“bearing site”) — likely bearing housings or assemblies from machinery.", 14, "Nos", ["bearing_scrap", "industrial_equipment"], 2, "Bearing Site Assorted, Qty-14 Nos"),
            _item("V", "Microscopes (21)", "Twenty-one **microscopes** — lab/optical equipment.", 21, "Nos", ["microscope", "mixed_ewaste"], 2, "Micro Scope Assorted, Qty-21 Nos"),
            _item("W", "Electric fans (300)", "Three hundred **electric fans** — ceiling/table/industrial types.", 300, "Nos", ["fan", "mixed_ewaste"], 2, "Fans Assorted, Qty-300 Nos"),
            _item("X", "Grass / branch cutters (21)", "Twenty-one **grass and tree-branch cutting machines** — gardening/grounds maintenance equipment.", 21, "Nos", ["grass_cutter", "industrial_equipment"], 2, "Grass / Tree Branch Cutting Machines ... Qty-21 Nos"),
            _item("Y", "Vacuum / deck cleaners (10)", "Ten **vacuum cleaners and deck-cleaning machines** — industrial cleaning equipment.", 10, "Nos", ["vacuum_cleaner", "mixed_ewaste"], 2, "Vaccum Cleaner / Deck cleaning Machines ... Qty-10 Nos"),
            _item("Z", "Mattresses (approx. 1,000)", "About **one thousand foam/coir mattresses** — bedding from barracks or offices. Difficult to resell; often a disposal cost rather than value.", 1000, "Nos", ["mattress", "foam_mattress", "coir_mattress"], 2, "Foam / Coir Mattress Assorted, Qty - ~1000 Nos", "Tender says ~1000"),
        ],
    },
    {
        "lot_code": "3A",
        "lot_summary_plain": (
            "A **mixed metal and miscellaneous stores lot**. You get nearly **6 tonnes of metal scrap** "
            "(bearings, aluminium, brass, general MT scrap), **600 brass couplings**, plus non-metal items: "
            "250 filters, 30 life rafts, 200 chairs, and **2,000 mattresses**. The metals are straightforward "
            "scrap for melting; the rafts, chairs and mattresses add bulk that may be hard to monetise."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 200000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": None,
        "document_pages": [2],
        "items": [
            _item("A", "Bearing scrap (2.5 MT)", "Two and a half **tonnes of bearing scrap** — worn ball/roller bearings and bearing steel for melting.", 2.5, "MT", ["bearing_scrap", "hms_iron"], 2, "Bearing Scrap, Qty - 2.5 MT"),
            _item("B", "Aluminium scrap (1 MT)", "One **tonne of aluminium scrap**, with or without attachments — window frames, sheets, mixed ali.", 1, "MT", ["aluminium_scrap", "aluminium"], 2, "Aluminium Scrap ... Qty-1 MT"),
            _item("C", "Brass couplings (600 pieces)", "Six hundred **brass coupling fittings** — plumbing/pipe fittings, sold by piece count.", 600, "Nos", ["brass_coupling", "brass"], 2, "Brass Coupling Assorted, Qty - 600 Nos"),
            _item("D", "Brass boring scrap (1 MT)", "One **tonne of brass boring/swarf** — brass turnings from machining.", 1, "MT", ["brass_boring", "brass"], 2, "Brass Boring Scrap, Qty-01 MT"),
            _item("E", "General MT scrap (1 MT)", "One **tonne of general mild-steel (MT) scrap** — ordinary iron/steel for melting.", 1, "MT", ["mt_scrap", "hms_iron"], 2, "MT Scrap, Qty-01 MT"),
            _item("F", "Filters (250)", "Two hundred fifty **assorted filters** — oil/air/water filters from equipment; may contain residue.", 250, "Nos", ["filter", "industrial_equipment"], 2, "Filters Assorted, Qty-250 Nos"),
            _item("G", "Life rafts (30)", "Thirty **life rafts** — inflatable marine survival rafts; may need specialised disposal or refurbishment.", 30, "Nos", ["life_raft", "industrial_equipment"], 2, "Life Rafts Assorted, Qty-30 Nos"),
            _item("H", "Chairs (200)", "Two hundred **assorted chairs** — office or mess furniture.", 200, "Nos", ["chair", "industrial_equipment"], 2, "Chairs Assorted, Qty - 200 Nos"),
            _item("J", "Mattresses (2,000)", "Two thousand **foam/coir mattresses** — very large bedding disposal component.", 2000, "Nos", ["mattress", "foam_mattress"], 2, "Foam / Coir Mattress Assorted, Qty -2000 Nos"),
        ],
    },
    {
        "lot_code": "4A",
        "lot_summary_plain": (
            "Three hundred **used vehicle tyres**, sold **by count** (not by weight). "
            "Typical scrap-dealer lot for retreading, crumb rubber, or pyrolysis — CPCB rules may apply for bulk tyres."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 50000,
        "unit_of_sale": "By Count (per tyre lot)",
        "regulatory_notes": None,
        "document_pages": [3],
        "items": [
            _item("A", "Used tyres (300)", "Three hundred **assorted used tyres** — cars/trucks mixed; condition not specified.", 300, "Nos", ["tyres", "tyre"], 3, "Tyres Assorted, Qty-300 Nos"),
        ],
    },
    {
        "lot_code": "5A",
        "lot_summary_plain": (
            "Heavy **industrial plant**: one large **400 kW Cummins diesel generator engine**, a **30-ton RT crane**, "
            "a **10-ton hydraulic mobile crane**, plus **20 tonnes of wood scrap**. This is high-value machinery "
            "sold for reuse or breaking — not a simple scrap-metal lot."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 200000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": None,
        "document_pages": [3],
        "items": [
            _item("A", "400 kW Cummins diesel engine (1)", "One **400 kW mobile diesel engine** (Cummins make) — large power-unit for generators or industrial drive.", 1, "No", ["diesel_engine", "crane", "industrial_equipment"], 3, "400KW Mobile Diesel Engine ... Qty-01 No"),
            _item("B", "30-ton RT crane (1)", "One **RT 740B rough-terrain crane, 30 ton capacity**, serial no. 91629 — full crane machine.", 1, "No", ["crane", "industrial_equipment"], 3, "RT 740B Crane (30 Ton) ... Qty-01 No"),
            _item("C", "10-ton hydraulic crane (1)", "One **10-ton hydraulic mobile crane** (TIL make), serial no. 13372.", 1, "No", ["crane", "industrial_equipment"], 3, "Hydraulic Mobile Crane (10 Ton) ... Qty-01 No"),
            _item("D", "Wood scrap (20 MT)", "Twenty **tonnes of wooden scrap** — timber/packing wood for fuel or recycling.", 20, "MT", ["wood_scrap"], 3, "Wood Scrap, Qty-20 MT"),
        ],
    },
    {
        "lot_code": "6A",
        "lot_summary_plain": (
            "Small **machinery lot**: two **engines** (likely diesel/industrial) and four **Genie brand lifts** "
            "(aerial work platforms / material lifts used for maintenance work)."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 200000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": None,
        "document_pages": [3],
        "items": [
            _item("A", "Engines (2)", "Two **assorted engines** — likely diesel units; purpose and power not detailed in tender.", 2, "Nos", ["engine", "industrial_equipment"], 3, "Engine Assorted, Qty-02 Nos"),
            _item("B", "Genie lifts (4)", "Four **Genie brand lifts** — typically scissor lifts or boom lifts for working at height.", 4, "Nos", ["genie", "industrial_equipment"], 3, "Genie Assorted, Qty-04 Nos"),
        ],
    },
    {
        "lot_code": "7A",
        "lot_summary_plain": (
            "**Marine small-craft lot**: three boats with engines, two motor boats (scooter type), and "
            "ten **outboard motors (OBM)**. Nautical equipment — resale to fishermen/boat yards or scrap."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 100000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": None,
        "document_pages": [3],
        "items": [
            _item("A", "Boats with engine (3)", "Three **boats sold with engines attached** — small vessels, condition unknown.", 3, "Nos", ["boat", "industrial_equipment"], 3, "Boat with engine Assorted, Qty-03 Nos"),
            _item("B", "Motor boats / scooter boats (2)", "Two **motor boats (scooter-type)** — small fibreglass/metal craft.", 2, "Nos", ["motor_boat", "boat", "industrial_equipment"], 3, "Motor Boat (Scooter Boat) ... Qty-02 Nos"),
            _item("C", "Outboard motors (10)", "Ten **outboard motors (OBM)** — detachable boat engines.", 10, "Nos", ["obm", "industrial_equipment"], 3, "OBM Assorted, Qty-10 Nos"),
        ],
    },
    {
        "lot_code": "8A",
        "lot_summary_plain": (
            "Workshop and metal mix: **13 air compressors**, **4 submersible pumps**, **26 welding machines**, "
            "**2 tonnes of cupro-nickel** (non-ferrous alloy common in marine fittings), and **1,000 mattresses**. "
            "Good for a workshop buyer or non-ferrous scrap dealer; mattresses again add disposal bulk."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 300000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": None,
        "document_pages": [3],
        "items": [
            _item("A", "HP air compressors (13)", "Thirteen **high-pressure air compressors** — workshop/shipyard type.", 13, "Nos", ["air_compressor", "industrial_equipment"], 3, "HP Air Compressor Assorted, Qty-13 Nos"),
            _item("B", "Submersible pumps (4)", "Four **submersible water pumps**.", 4, "Nos", ["submersible_pump", "industrial_equipment"], 3, "Submersible Pumps Assorted, Qty-04 Nos"),
            _item("C", "Welding machines (26)", "Twenty-six **welding machines** — arc/MIG types for metal fabrication.", 26, "Nos", ["welding_machine", "industrial_equipment"], 3, "Welding Machines Assorted, Qty-26 Nos"),
            _item("D", "Cupro-nickel scrap (2 MT)", "Two **tonnes of cupro-nickel** — copper-nickel alloy scrap (valuable non-ferrous; common in marine pipe/fittings).", 2, "MT", ["cupro_nickel"], 3, "Cupro Nickle, Qty-02 MT"),
            _item("E", "Mattresses (1,000)", "One thousand **foam/coir mattresses**.", 1000, "Nos", ["mattress", "foam_mattress"], 3, "Foam / Coir Mattress Assorted, Qty -1000 Nos"),
        ],
    },
    {
        "lot_code": "9A",
        "lot_summary_plain": (
            "Fifty **metric tonnes of electrical scrap** (“W/T Electrical Scrap”) — bulk copper/aluminium-bearing "
            "wire, panels, and mixed electrical waste. This is a **weight-based scrap lot** (sold by the tonne), "
            "not individual items. **CPCB certificate required** — same rules as lot 2A."
        ),
        "location": _LOC,
        "contact": _CONTACT,
        "pre_bid_emd_inr": 500000,
        "unit_of_sale": "By Weight (50 MT total)",
        "regulatory_notes": "CPCB / MOEF / State PCB certificate mandatory. Lots 2A and 9A restricted to certified recyclers.",
        "document_pages": [3],
        "items": [
            _item(
                "A", "Electrical scrap (50 MT)",
                "Fifty **metric tonnes of mixed electrical scrap** — cables, switchgear, panels, and wire-rich waste "
                "typical of shipyard/establishment electrical clearance. Valued by weight at scrap yards.",
                50, "MT", ["wt_electrical", "electrical_scrap"], 3,
                "W/T Electrical Scrap, Qty-50 MT",
            ),
        ],
    },
]

ARCHIVES: dict[str, list[dict[str, Any]]] = {"31705": ARCHIVE_31705}


def get_archive_catalog(auction_id: str) -> list[dict[str, Any]]:
    from scraper.gem_analysis.catalog_store import get_archive_catalog as _load

    return _load(auction_id)
