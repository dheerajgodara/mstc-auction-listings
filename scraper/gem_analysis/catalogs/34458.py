"""Hand-crafted archive catalog for auction 34458 (CTS/3211/DISP/26-27/06/Scrap)."""

from __future__ import annotations

from typing import Any

_LOC_OLD = "MO(V) / OLD SITE, Visakhapatnam"
_CONTACT_OLD = "0891-2815089 / 5095"
_CPCB = "CPCB / MOEF / State PCB certificate mandatory (Lots 4A & 8A)"


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


ARCHIVE_34458: list[dict[str, Any]] = [
    {
        "lot_code": "1A",
        "lot_summary_plain": (
            "**Lot 1A** is a **heavy industrial scrap bundle** at the Navy Material Organisation old depot, Visakhapatnam. "
            "You are buying **40 tonnes of machinery scrap**, **150 tonnes of iron scrap**, gas cylinders on trolleys, "
            "assorted small plant items, **seven engines**, and **twelve hand trolleys** — all as one lot. "
            "This is primarily **melting and dismantling** material, not sorted retail scrap. Pre-bid EMD is **₹10 lakh**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 1000000,
        "unit_of_sale": "By Lot",
        "document_pages": [2],
        "items": [
            _item(
                "A", "Machinery scrap (40 MT)",
                "Forty metric tonnes of **broken machinery and plant metal** — frames, shafts, and equipment too large "
                "or mixed to count piece by piece. Sold for cutting and melting.",
                40, "MT", ["machinery_scrap", "hms_iron"], 2, "(A) Machinery Scrap, Qty-40 MT",
            ),
            _item(
                "B", "Iron scrap (150 MT)",
                "One hundred fifty tonnes of **heavy iron/steel scrap (HMS)** — the main weight line in this lot. "
                "Typical use: induction furnace or steel yard melting.",
                150, "MT", ["hms_iron", "mt_scrap"], 2, "(B) Iron Scrap, Qty-150 MT",
            ),
            _item(
                "C", "Trolley-mounted gas cylinders (10 nos, ~75 kg type)",
                "Ten **large gas cylinders mounted on wheeled trolleys** (about 75 kg capacity type). "
                "Industrial gas bottles; may contain residue — handle per safety rules.",
                10, "Nos", ["gas_cylinder", "industrial_equipment"], 2,
                "(C) Trolley Mounted Cylinders (75 Kgs) Assorted, Qty-10 Nos.",
            ),
            _item(
                "D", "Assorted CEE / plant items (200 nos)",
                "Two hundred **miscellaneous plant items** listed as CEE assorted in the tender — small equipment "
                "and fittings sold piece-count, condition unknown.",
                200, "Nos", ["industrial_equipment"], 2, "(D) cee Assorted, Qty-200 Nos",
            ),
            _item(
                "E", "Engines assorted (7 nos)",
                "Seven **engine units** — likely diesel or industrial engines. Useful for parts, rebuild, or scrap "
                "depending on make and condition.",
                7, "Nos", ["engine", "industrial_equipment"], 2, "(E) Engines Assorted, Qty-07 Nos",
            ),
            _item(
                "F", "Hand trolleys (12 nos)",
                "Twelve **manual hand-pushed trolleys** for moving stores inside workshops and warehouses.",
                12, "Nos", ["hand_trolley", "industrial_equipment"], 2, "(F) Hand Trolley Assorted, Qty-12 Nos.",
            ),
        ],
    },
    {
        "lot_code": "2A",
        "lot_summary_plain": (
            "**Lot 2A** is **specialist workshop machinery** at MO(V) Old Site — not bulk scrap. "
            "It includes a **3-tonne-capacity rotor balancing machine**, a **complete induction regulator set** "
            "(two units, ~1100 kg capacity), and a **1-ton vertical universal shearing/punching machine**. "
            "Buyers typically refurbish or strip these for resale. EMD **₹3 lakh**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 300000,
        "unit_of_sale": "By Lot",
        "document_pages": [2],
        "items": [
            _item(
                "A", "Rotor balancing machine (3000 kg capacity, 1 no)",
                "One **industrial rotor balancing machine** rated for rotors up to about **3000 kg**. "
                "Used to balance large rotating parts (motors, turbines). Heavy fixed plant.",
                1, "No", ["balancing_machine", "industrial_equipment"], 2,
                "(A) Rotor Balancing Machine Assorted (3000 Kg Capacity), Qty-01 No.",
            ),
            _item(
                "B", "Induction regulator complete set (1100 kg, 2 nos)",
                "Two **induction regulator units** as a complete set, each around **1100 kg capacity** — "
                "electrical power-conditioning equipment for industrial use.",
                2, "Nos", ["induction_regulator", "industrial_equipment"], 2,
                "(B) Induction Regulator (Complete Set) Assorted (1100 Kgs Capacity), Qty-02 Nos.",
            ),
            _item(
                "C", "Vertical universal shearing / punching machine (1 ton, 1 no)",
                "One **vertical universal shearing and punching machine** with about **1-ton capacity** — "
                "sheet-metal workshop press for cutting and punching plate.",
                1, "No", ["sheet_metal_machine", "industrial_equipment"], 2,
                "(C) Vertical Universal Sharing Punching, Cropping & Machine Assorted (01 Ton Capacity), Qty-01 No.",
            ),
        ],
    },
    {
        "lot_code": "3A",
        "lot_summary_plain": (
            "**Lot 3A** is **200 assorted used tyres** at MO(V) Old Site. "
            "Only firms with a valid **CPCB / pollution-board certificate** may bid. "
            "Tyres are sold for retreading, crumb rubber, or licensed disposal — not as road-ready stock."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 30000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": _CPCB,
        "document_pages": [2],
        "items": [
            _item(
                "A", "Tyres assorted (200 nos)",
                "Two hundred **used vehicle tyres** of mixed sizes and brands. "
                "Environmental rules apply; authorised recyclers only.",
                200, "Nos", ["tyres", "tyre"], 2, "Tyres Assorted, Qty-200 Nos",
            ),
        ],
    },
    {
        "lot_code": "4A",
        "lot_summary_plain": (
            "**Lot 4A** is the largest **e-waste and office-equipment lot** in this auction — **24 sub-lines** "
            "from projectors and laptops to **700 computers**, **250 televisions**, **300 fans**, and **1000 mattresses**. "
            "Located at MO(V) Old Site. **CPCB certificate required.** Pre-bid EMD **₹1 lakh**. "
            "This lot is typical of a full depot clear-out of IT, AV, and mess equipment."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 100000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": _CPCB,
        "document_pages": [2],
        "items": [
            _item("A", "Projectors (15 nos)", "Fifteen **data/video projectors** — meeting-room and training AV equipment.", 15, "Nos", ["projector", "mixed_ewaste"], 2, "(A) Projectors Assorted, Qty-15 Nos"),
            _item("B", "Laptops (11 nos)", "Eleven **laptop computers** — mixed-condition IT e-waste.", 11, "Nos", ["laptop", "mixed_ewaste"], 2, "(B) Laptops Assorted, Qty-11 Nos"),
            _item("C", "Binoculars (135 nos)", "One hundred thirty-five **optical binoculars** — surveillance/navigation optics.", 135, "Nos", ["binocular", "mixed_ewaste"], 2, "(C) Binoculars Assorted, Qty-135 Nos"),
            _item("D", "Televisions (250 nos)", "Two hundred fifty **television sets** — bulk LCD/LED disposal line.", 250, "Nos", ["television", "mixed_ewaste"], 2, "(D) Television Assorted, Qty-250 Nos"),
            _item("E", "Cameras (15 nos)", "Fifteen **still/video cameras** — photographic equipment.", 15, "Nos", ["camera", "mixed_ewaste"], 2, "(E) Camera Assorted, Qty-15 Nos"),
            _item("F", "CCTV cameras (20 nos)", "Twenty **CCTV security cameras** — surveillance hardware.", 20, "Nos", ["cctv", "mixed_ewaste"], 2, "(F) CCTV Camera Assorted, Qty-20 Nos"),
            _item("G", "Thermal imaging cameras (6 nos)", "Six **thermal imaging cameras** — specialised night/heat vision gear.", 6, "Nos", ["thermal_camera", "mixed_ewaste"], 2, "(G) Thermal imaging Camera Assorted, Qty-06 Nos"),
            _item("H", "Water purifiers (150 nos)", "One hundred fifty **water purifier units** — RO/UV domestic or mess units.", 150, "Nos", ["water_purifier", "mixed_ewaste"], 2, "(H) Water Purifier Assorted, Qty- 150 Nos."),
            _item("J", "Computers / all-in-one PCs (700 nos)", "Seven hundred **desktop and all-in-one personal computers** — major IT e-waste volume.", 700, "Nos", ["computer", "mixed_ewaste"], 2, "(J) Computers / All in One Personal computer Assorted, Qty-700 Nos"),
            _item("K", "Printers (100 nos)", "One hundred **printers** — inkjet/laser office machines.", 100, "Nos", ["printer", "mixed_ewaste"], 2, "(K) Printers Assorted, Qty-100 Nos."),
            _item("L", "Xerox / photocopiers (50 nos)", "Fifty **photocopy machines** — high-toner office equipment.", 50, "Nos", ["xerox", "printer", "mixed_ewaste"], 2, "(L) Xerox Machine Assorted, Qty-50 Nos."),
            _item("M", "Air conditioners (50 nos)", "Fifty **air-conditioning units** — refrigerant-bearing white goods.", 50, "Nos", ["air_conditioner", "mixed_ewaste"], 2, "(M) Arcana Assorted, Qty-50 Nos."),
            _item("N", "Refrigerators (30 nos)", "Thirty **refrigerators** — compressor and refrigerant handling applies.", 30, "Nos", ["refrigerator", "mixed_ewaste"], 2, "(N) Refrigerators Assorted, Qty-30 Nos"),
            _item("P", "Washing machines (20 nos)", "Twenty **washing machines** — domestic/laundry appliances.", 20, "Nos", ["washing_machine", "mixed_ewaste"], 2, "(P) Washing Machines Assorted, Qty-20 Nos"),
            _item("Q", "Microwave ovens (25 nos)", "Twenty-five **microwave ovens** — small kitchen appliances.", 25, "Nos", ["microwave", "mixed_ewaste"], 2, "(Q) Micro Ovens Assorted, Qty-25 Nos"),
            _item("R", "Geysers (10 nos)", "Ten **electric water geysers** — mess/bathroom heaters.", 10, "Nos", ["geyser", "mixed_ewaste"], 2, "(R) Geysers Assorted, Qty-10 Nos"),
            _item("S", "Generators (8 nos)", "Eight **portable or standby generators** — diesel/petrol sets.", 8, "Nos", ["generator", "industrial_equipment"], 2, "(S) Generators Assorted, Qty-08 Nos"),
            _item("T", "Sextants (6 nos)", "Six **marine sextants** — nautical navigation instruments.", 6, "Nos", ["sextant", "mixed_ewaste"], 2, "(T) Sextant Assorted, Qty-06 Nos"),
            _item("U", "Bearing site assorted (14 nos)", "Fourteen **bearing-related site items** — housings or bearing assemblies.", 14, "Nos", ["bearing", "industrial_equipment"], 2, "(U) Bearing Site Assorted, Qty-14 Nos"),
            _item("V", "Microscopes (21 nos)", "Twenty-one **microscopes** — lab/optical equipment.", 21, "Nos", ["microscope", "mixed_ewaste"], 2, "(V) Micro Scope Assorted, Qty-21 Nos"),
            _item("W", "Fans (300 nos)", "Three hundred **electric fans** — ceiling, table, or pedestal types mixed.", 300, "Nos", ["fan", "mixed_ewaste"], 2, "(W) Fans Assorted, Qty-300 Nos"),
            _item("X", "Grass / tree branch cutting machines (21 nos)", "Twenty-one **garden/grounds cutting machines** — branch chippers or grass cutters.", 21, "Nos", ["garden_machine", "industrial_equipment"], 2, "(X) Grass / Tree Branch Cutting Machines Assorted - Qty-21 Nos."),
            _item("Y", "Vacuum / deck cleaning machines (10 nos)", "Ten **vacuum or deck-cleaning machines** — industrial or ship-deck cleaners.", 10, "Nos", ["vacuum_cleaner", "mixed_ewaste"], 2, "(Y) Vaccum Cleaner / Deck cleaning Machines Assorted, Qty-10 Nos"),
            _item("Z", "Foam / coir mattresses (1000 nos)", "One thousand **foam or coir mattresses** — bedding bulk; costly to landfill.", 1000, "Nos", ["mattress", "foam_mattress"], 2, "(Z) Foam / Coir Mattress Assorted, Qty -1000 Nos"),
        ],
    },
    {
        "lot_code": "5A",
        "lot_summary_plain": (
            "**Lot 5A** mixes **non-ferrous metals**, **bearing scrap**, filters, **30 life rafts**, furniture, and **2000 mattresses**. "
            "Key weights: **2.5 MT bearing scrap**, **1 MT aluminium**, brass boring and couplings, **1 MT MT scrap**. "
            "EMD **₹7 lakh** at MO(V) Old Site."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 700000,
        "unit_of_sale": "By Lot",
        "document_pages": [3],
        "items": [
            _item("A", "Bearing scrap (2.5 MT)", "Two and a half tonnes of **bearing steel scrap** — alloy rings and housings.", 2.5, "MT", ["bearing_scrap"], 3, "(A) Bearing Scrap, Qty - 2.5 MT"),
            _item("B", "Aluminium scrap (1 MT)", "One tonne **aluminium scrap** with or without attachments — window frames, sheet, mixed ali.", 1, "MT", ["aluminium_scrap"], 3, "(B) Aluminium Scrap (with / without Attachment), Qty-1 MT"),
            _item("C", "Brass couplings (600 nos)", "Six hundred **brass coupling fittings** — yellow-metal hardware.", 600, "Nos", ["brass"], 3, "(C) Brass Coupling Assorted, Qty - 600 Nos"),
            _item("D", "Brass boring scrap (1 MT)", "One tonne **brass boring/swarf** from machining.", 1, "MT", ["brass"], 3, "(D) Brass Boring Scrap, Qty-01 MT"),
            _item("E", "MT scrap (1 MT)", "One tonne **miscellaneous metal (MT) scrap** — general melt stock.", 1, "MT", ["mt_scrap"], 3, "(E) MT Scrap, Qty-01 MT"),
            _item("F", "Filters assorted (250 nos)", "Two hundred fifty **industrial filters** — oil/air types from equipment.", 250, "Nos", ["filter", "industrial_equipment"], 3, "(F) Filters Assorted, Qty-250 Nos."),
            _item("G", "Life rafts (30 nos)", "Thirty **inflatable marine life rafts** — safety equipment; specialised handling.", 30, "Nos", ["life_raft", "marine_equipment"], 3, "(G) Life Rafts Assorted, Qty-30 Nos"),
            _item("H", "Chairs (200 nos)", "Two hundred **chairs** — office or mess seating.", 200, "Nos", ["chair", "furniture"], 3, "(H) Chairs Assorted, Qty - 200 Nos"),
            _item("J", "Foam / coir mattresses (2000 nos)", "Two thousand **mattresses** — large bedding disposal volume.", 2000, "Nos", ["mattress", "foam_mattress"], 3, "(J) Foam / Coir Mattress Assorted, Qty -2000 Nos"),
        ],
    },
    {
        "lot_code": "6A",
        "lot_summary_plain": (
            "**Lot 6A** is **workshop plant**: **13 HP air compressors**, **4 submersible pumps**, **26 welding machines**, "
            "**2 MT cupro-nickel scrap**, plus **1000 mattresses**. High reuse value on machines. EMD **₹2.9 lakh**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 290000,
        "unit_of_sale": "By Lot",
        "document_pages": [3],
        "items": [
            _item("A", "HP air compressors (13 nos)", "Thirteen **high-pressure air compressors** for workshops and ship systems.", 13, "Nos", ["compressor", "industrial_equipment"], 3, "(A) HP Air Compressor Assorted, Qty-13 Nos"),
            _item("B", "Submersible pumps (4 nos)", "Four **submersible water pumps** — dewatering or bore-well type.", 4, "Nos", ["pump", "industrial_equipment"], 3, "(B) Submersible Pumps Assorted, Qty-04 Nos"),
            _item("C", "Welding machines (26 nos)", "Twenty-six **arc/MIG welding sets** — standard shipyard workshop kit.", 26, "Nos", ["welding_machine", "industrial_equipment"], 3, "(C) Welding Machines Assorted, Qty-26 Nos"),
            _item("D", "Cupro-nickel (2 MT)", "Two tonnes **cupro-nickel alloy scrap** — valuable marine-grade metal.", 2, "MT", ["cupro_nickel"], 3, "(D) Cupro Nickle, Qty-02 MT"),
            _item("E", "Foam / coir mattresses (1000 nos)", "One thousand **mattresses** bundled with workshop lot.", 1000, "Nos", ["mattress", "foam_mattress"], 3, "(E) Foam / Coir Mattress Assorted, Qty -1000 Nos"),
        ],
    },
    {
        "lot_code": "7A",
        "lot_summary_plain": (
            "**Lot 7A** has **DC electrical workshop machines** — two balancing machines, one converter, one DC motor. "
            "**CPCB certificate required.** EMD **₹30,000**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 30000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": _CPCB,
        "document_pages": [3],
        "items": [
            _item("A", "DC balancing machines (2 nos)", "Two **DC-type balancing machines** for rotating equipment.", 2, "Nos", ["balancing_machine", "industrial_equipment"], 3, "(A) DC Balancing Machine, Qty-02 Nos."),
            _item("B", "Converter assorted (1 no)", "One **electrical converter unit** — power conversion for DC plant.", 1, "No", ["converter", "industrial_equipment"], 3, "(B) Convertor Assorted, Qty-01 No."),
            _item("C", "DC electric motor (1 no)", "One **DC electric motor** — standalone drive unit.", 1, "No", ["dc_motor", "industrial_equipment"], 3, "(C) DC Electric Motor Assorted, Qty-01 No."),
        ],
    },
    {
        "lot_code": "8A",
        "lot_summary_plain": (
            "**Lot 8A** is the **highest-value line** in this auction: **528 submarine batteries** plus **2000 mattresses**. "
            "Submarine batteries are very large **lead-acid (or similar) cells** — extreme weight and **hazardous-waste rules**. "
            "Only **CPCB-authorised** firms may bid. Pre-bid EMD **₹50 lakh**."
        ),
        "location": _LOC_OLD,
        "contact": _CONTACT_OLD,
        "pre_bid_emd_inr": 5000000,
        "unit_of_sale": "By Lot",
        "regulatory_notes": _CPCB,
        "document_pages": [3],
        "items": [
            _item(
                "A", "Submarine batteries (528 nos)",
                "Five hundred twenty-eight **submarine/ship battery cells** — among the heaviest and most regulated "
                "items in Indian Navy scrap auctions. Requires licensed transport and recycling.",
                528, "Nos", ["lead_acid_battery", "submarine_battery"], 3,
                "(A) Submarine Batteries, Qty-528 Nos",
            ),
            _item("B", "Foam / coir mattresses (2000 nos)", "Two thousand **mattresses** sold in the same lot as the batteries.", 2000, "Nos", ["mattress", "foam_mattress"], 3, "(B) Foam / Coir Mattress Assorted, Qty -2000 Nos"),
        ],
    },
    {
        "lot_code": "9A",
        "lot_summary_plain": (
            "**Lot 9A** spans **two Naval Dockyard sites**: an **EOT crane (15/3 ton)** at ND(V)/MSAX and "
            "**12,000 empty H₂SO₄ glass bottles** at ND(V)/MECE. Crane is tracked equipment with survey number; "
            "bottles are low-value lab waste. EMD **₹50,000**."
        ),
        "location": "ND(V)/ MSAX & ND(V)/ MECE, Visakhapatnam",
        "contact": "MSAX: 9246156575 / 0891-2816672; MECE: Mr. Hari 9948062747",
        "pre_bid_emd_inr": 50000,
        "unit_of_sale": "By Lot",
        "document_pages": [3],
        "items": [
            _item(
                "A", "EOT crane 15/3 ton (1 no)",
                "One **electric overhead travelling (EOT) crane** rated **15/3 tonne** — full gantry crane for dockyard halls. "
                "Survey No. 20252368P0004.",
                1, "No", ["crane", "eot_crane", "industrial_equipment"], 3,
                "(A) EOT Crane (15/3 Ton) Assorted, Qty-01 No. (Srvy No. 20252368P0004)",
            ),
            _item(
                "B", "H₂SO₄ empty glass bottles (12,000 nos)",
                "Twelve thousand **empty sulphuric acid glass bottles** — laboratory containers; "
                "minimal scrap value but careful handling. Survey No. 20262368G0067NONMO.",
                12000, "Nos", ["glass_bottle", "lab_waste"], 3,
                "(B) H2SO4 Empty Glass Bottles, Qty-12000 Nos.",
            ),
        ],
    },
    {
        "lot_code": "10A",
        "lot_summary_plain": (
            "**Lot 10A** is a **1-ton EOT crane** at ND(V)/DM(Weapons), Visakhapatnam. "
            "Contact Mr. K Sambasivarao. Sold **by count** (single machine). EMD **₹20,000**."
        ),
        "location": "ND(V) / DM(Weapons), Visakhapatnam",
        "contact": "K Sambasivarao, PH. 9989802850",
        "pre_bid_emd_inr": 20000,
        "unit_of_sale": "By Count",
        "document_pages": [3],
        "items": [
            _item(
                "A", "EOT crane 1 ton (1 no)",
                "One **1-tonne EOT crane** — smaller overhead crane for weapons/workshop bay. "
                "Survey No. 20262368G0260NONMO.",
                1, "No", ["crane", "eot_crane", "industrial_equipment"], 3,
                "EOT Crane Assorted (01 Ton), Qty-01 No. (Srvy No. 20262368G0260NONMO)",
            ),
        ],
    },
    {
        "lot_code": "11A",
        "lot_summary_plain": (
            "**Lot 11A** is a **small mixed scrap and IT lot** at **Naval Liaison Cell, Hyderabad** — "
            "electrical scrap (UPS, RAM, motherboards), cameras, printers, chairs, and minor metal/plastic weights. "
            "Typical of a liaison office clear-out. EMD **₹5,000**."
        ),
        "location": "Naval Liaison Cell, Hyderabad",
        "contact": "Cdr Satish, PH: 9427968639",
        "pre_bid_emd_inr": 5000,
        "unit_of_sale": "By Lot",
        "document_pages": [4],
        "items": [
            _item(
                "A", "W/T electrical scrap (65.5 kg)",
                "Sixty-five kg of **wireless/telecom electrical scrap** — UPS units (1 kVA APC etc.), RAM, "
                "motherboards, hard disks, ethernet cards. Copper-bearing e-waste.",
                65.5, "Kgs", ["electrical_scrap", "wt_electrical", "mixed_ewaste"], 4,
                "(A) WIT Electrical Scrap, Qty-65.5 Kgs",
            ),
            _item("B", "Camera (1 no)", "One **camera** — photographic equipment.", 1, "No", ["camera", "mixed_ewaste"], 4, "(B) Camera Assorted, Qty-01 No."),
            _item("C", "Vacuum cleaner (1 no)", "One **vacuum cleaner**.", 1, "No", ["vacuum_cleaner", "mixed_ewaste"], 4, "(C) Vaccum Cleaner Assorted, Qty-01 No."),
            _item(
                "D", "Plastic scrap (7.9 kg)",
                "Seven point nine kg **plastic scrap** from scanner, emergency lamp, shredder, cordless phone, etc.",
                7.9, "Kgs", ["plastic_scrap", "mixed_ewaste"], 4,
                "(D) Plastic Scrap, Qty-7.9 Kgs",
            ),
            _item("E", "Iron scrap (18.5 kg)", "Eighteen kg **iron scrap** including bicycle and folding umbrella frame.", 18.5, "Kgs", ["hms_iron"], 4, "(E) Iron Scrap, Qty-18.5 Kgs"),
            _item("F", "Stainless steel scrap (1 kg)", "One kg **stainless steel scrap**.", 1, "Kg", ["ss_scrap"], 4, "(F) S S Scrap, Qty- 1 Kg"),
            _item("G", "Printers (2 nos)", "Two **printers**.", 2, "Nos", ["printer", "mixed_ewaste"], 4, "(G) Printer Assorted, Qty-02 Nos"),
            _item("H", "Chairs (17 nos)", "Seventeen **chairs**.", 17, "Nos", ["chair", "furniture"], 4, "(H) Chairs Assorted, Qty-17 Nos"),
            _item("J", "Tool scrap (600 g)", "Six hundred grams **tool scrap** from arboriculture equipment.", 0.6, "Kgs", ["tool_scrap"], 4, "(J) Tool Scrap, Qty-600 Grms"),
            _item("K", "Personal computers (3 nos)", "Three **desktop PCs**.", 3, "Nos", ["computer", "mixed_ewaste"], 4, "(K) Personal Computer Assorted, Qty-03 Nos"),
            _item("L", "Xerox machine (1 no)", "One **photocopier**.", 1, "No", ["xerox", "printer", "mixed_ewaste"], 4, "(L) Xerox Machine Assorted, Qty-01 No."),
        ],
    },
    {
        "lot_code": "12A",
        "lot_summary_plain": (
            "**Lot 12A** at **NAD, Sunabeda** is bulk **iron and wood scrap**: **16.31 MT iron** and **10.48 MT wooden scrap**. "
            "Standard melting and biomass/fuel-wood routes. EMD **₹1 lakh**."
        ),
        "location": "NAD, Sunabeda",
        "contact": "Mr KM Anoop Antony, SSS(A), PH. 8301949321",
        "pre_bid_emd_inr": 100000,
        "unit_of_sale": "By Lot",
        "document_pages": [4],
        "items": [
            _item("A", "Iron scrap (16.31 MT)", "Sixteen point three one tonnes **iron/steel scrap** for melting.", 16.31, "MT", ["hms_iron", "mt_scrap"], 4, "(A) Iron Scrap, Qty-16.31 MT"),
            _item("B", "Wooden scrap (10.48 MT)", "Ten point four eight tonnes **wooden scrap** — packing timber and wood waste.", 10.48, "MT", ["wood_scrap"], 4, "(B) Wooden Scrap, Qty-10.48 MT"),
        ],
    },
    {
        "lot_code": "13A",
        "lot_summary_plain": (
            "**Lot 13A** is **five assorted tyres** at **PIMT (AMBER), Hyderabad** — small tail lot. EMD **₹1,000**."
        ),
        "location": "PIMT, AMBER, Hyderabad",
        "contact": "Mr Pawan, LOG MAT., PH. 9705859746",
        "pre_bid_emd_inr": 1000,
        "unit_of_sale": "By Lot",
        "document_pages": [4],
        "items": [
            _item("A", "Tyres assorted (5 nos)", "Five **used tyres** — small quantity at Hyderabad training establishment.", 5, "Nos", ["tyres", "tyre"], 4, "Tyres Assorted, Qty-05 Nos"),
        ],
    },
]

LOTS = ARCHIVE_34458

META = {
    "reference_no": "CTS/3211/DISP/26-27/06/Scrap dated 01 Jun 26",
    "auction_date": "2026-06-01 to 2026-06-02",
    "region": "Visakhapatnam, Hyderabad, Sunabeda (multi-site)",
    "location_summary": "MO(V) Old Site Visakhapatnam; Naval Dockyard sites; NAD Sunabeda; Hyderabad liaison/PIMT",
}
