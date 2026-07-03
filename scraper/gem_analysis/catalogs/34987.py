"""Archive catalog for auction 34987 — 23 earth-moving plants in 10 lots (Indian Army)."""

from __future__ import annotations

from typing import Any

_GEM = {
    "01": "01 X JCB 3DX and 01 x Wheel Dozer",
    "02": "01 x SSL and 01 x TATA JD 315 SE",
    "03": "01 x Wheel Dozer",
    "04": "01 x TATA JD 315 SE",
    "05": "03 x Cr Tr Size II Dozer D80",
    "06": "03 x Cr Tr Size II Dozer D80  01 x SSL and 01 x Cr Tr Size IV Dozer D50",
    "07": "01 x TATA JD 315 SE",
    "08": "01 x Cr Tr Size II Dozer D80 and 01 x Motor Grader",
    "09": "03 x JCB 3DX 01 X Cr Tr Size II Dozer D80 and 01 x Cr Tr Size IV Dozer D50",
    "10": "01 x JBC 3DX",
}


def _ev(page: int, excerpt: str) -> dict[str, Any]:
    return {"source": "equipment_list_pdf", "page_no": page, "ocr_excerpt": excerpt}


def _eq(
    sub: str,
    title: str,
    plain: str,
    em_no: str,
    location: str,
    state: str,
    contact: str,
    page: int,
    excerpt: str,
) -> dict[str, Any]:
    return {
        "sub_code": sub,
        "title": title,
        "description_verbatim": f"{em_no} — {title} @ {location}, {state}",
        "plain_language": plain,
        "quantity": 1,
        "unit": "Plant",
        "material_tags": ["earth_moving_equipment", "plant_scrap", "industrial_equipment"],
        "evidence": _ev(page, excerpt),
        "plant_no": em_no,
        "location": location,
        "state": state,
        "contact": contact,
    }


def _lot(
    num: str,
    summary: str,
    items: list[dict[str, Any]],
    page: int,
) -> dict[str, Any]:
    return {
        "lot_code": num,
        "gem_item_name": _GEM[num],
        "lot_summary_plain": summary,
        "location": items[0].get("location", "India") if items else "Various",
        "unit_of_sale": "By Lot",
        "document_pages": [page],
        "items": items,
    }


ARCHIVE_34987: list[dict[str, Any]] = [
    _lot(
        "01",
        "**Lot 1** — **JCB 3DX backhoe loader** and **wheel dozer** at **Plant 201 Engr Regt, Jalandhar (Punjab)**. "
        "Two condemned army engineer plant vehicles sold together.",
        [
            _eq(
                "A", "JCB 3DX backhoe loader",
                "One **JCB 3DX** — a combined **backhoe and front loader** used for digging and loading. "
                "Army plant number **084108E**. Condemned engineer equipment.",
                "084108E", "Plant 201 Engr Regt, Jalandhar", "Punjab", "9677701493 / 800746",
                1, "084108E — JCB 3DX, Jalandhar",
            ),
            _eq(
                "B", "Wheel dozer",
                "One **wheeled bulldozer (wheel dozer)** — earth-moving blade on wheels rather than tracks. "
                "Plant **252 CEDU**.",
                "080263K", "Plant 252 CEDU, Jalandhar", "Punjab", "97526001",
                1, "080263K — Wheel Dozer",
            ),
        ],
        1,
    ),
    _lot(
        "02",
        "**Lot 2** at **Plant 4 Engr Regt, Leh (Ladakh)** — **skid-steer loader (SSL)** plus **Tata-John Deere 315 SE excavator**.",
        [
            _eq(
                "A", "Skid-steer loader (SSL)",
                "One **SSL skid-steer loader** — compact loader for tight sites; common in army plant parks.",
                "087179K", "Plant 4 Engr Regt, Leh", "Ladakh", "73068389",
                1, "087179K — SSL, Leh",
            ),
            _eq(
                "B", "Tata JD 315 SE MK-I excavator",
                "One **Tata-John Deere 315 SE** hydraulic **excavator** (MK-I series) — tracked digger for earth work.",
                "084602E", "Plant 4 Engr Regt, Leh", "Ladakh", "73068389",
                1, "084602E — TATA JD 315 SE MK-I",
            ),
        ],
        1,
    ),
    _lot(
        "03",
        "**Lot 3** — single **wheel dozer** at **Plant 20 Engr Regt, Mathura Cantt (UP)**.",
        [
            _eq(
                "A", "Wheel dozer",
                "One **wheel dozer** condemned at Mathura engineer regiment plant.",
                "080295M", "Plant 20 Engr Regt, Mathura Cantt", "UP", "96226637 / 79784591",
                1, "080295M — Wheel Dozer, Mathura",
            ),
        ],
        1,
    ),
    _lot(
        "04",
        "**Lot 4** — **Tata JD 315 SE excavator** at **439 (I) Engr Sqn, Nyoma (Ladakh)**.",
        [
            _eq(
                "A", "Tata JD 315 SE MK-I excavator",
                "One **Tata-John Deere 315 SE** excavator at high-altitude engineer squadron location.",
                "084403E", "Plant 439 (I) Engr Sqn, Nyoma", "Ladakh", "73888179 / 97950047",
                1, "084403E — TATA JD 315 SE, Nyoma",
            ),
        ],
        1,
    ),
    _lot(
        "05",
        "**Lot 5** — **three Caterpillar D80 crawler dozers** at **Plant 651 EPU, Nagrota (J&K)**.",
        [
            _eq("A", "CAT D80 crawler dozer (Size II)", "Caterpillar **Size II D80 track dozer** — heavy crawler bulldozer.", "060619L", "Plant 651 EPU, Nagrota", "J&K", "60060257", 2, "060619L — Cr Tr D80"),
            _eq("B", "CAT D80 crawler dozer (Size II)", "Second **D80 track dozer** in same lot.", "060690Y", "Plant 651 EPU, Nagrota", "J&K", "60060257", 2, "060690Y — Cr Tr D80"),
            _eq("C", "CAT D80 crawler dozer (Size II)", "Third **D80 track dozer**.", "060541L", "Plant 651 EPU, Nagrota", "J&K", "60060257", 2, "060541L — Cr Tr D80"),
        ],
        2,
    ),
    _lot(
        "06",
        "**Lot 6** at **Plant 116 Engr Regt, Bareilly Cantt (UP)** — **three D80 dozers**, one **SSL**, and one **CAT D50 dozer**. "
        "Largest mixed plant lot; H1 **accepted** at ₹34.61 lakh.",
        [
            _eq("A", "CAT D80 crawler dozer", "Caterpillar **D80** track dozer.", "060500F", "Plant 116 Engr Regt, Bareilly", "UP", "62838248", 2, "060500F"),
            _eq("B", "CAT BD80 crawler dozer", "**BD80** variant crawler dozer.", "060333W", "Plant 116 Engr Regt, Bareilly", "UP", "84278471", 2, "060333W"),
            _eq("C", "CAT BD80 crawler dozer", "Third **BD80** dozer.", "060523H", "Plant 116 Engr Regt, Bareilly", "UP", "84278471", 2, "060523H"),
            _eq("D", "Skid-steer loader (SSL)", "One **SSL** compact loader.", "087098M", "Plant 116 Engr Regt, Bareilly", "UP", "84278471", 2, "087098M"),
            _eq("E", "CAT D50 crawler dozer (Size IV)", "Caterpillar **Size IV D50** — smaller track dozer than D80.", "070084W", "Plant 116 Engr Regt, Bareilly", "UP", "84278471", 2, "070084W"),
        ],
        2,
    ),
    _lot(
        "07",
        "**Lot 7** — **Tata JD 315 SE excavator** at **Plant 235 Engr Regt, Akhnoor (J&K)**.",
        [
            _eq("A", "Tata JD 315 SE MK-I excavator", "One **Tata-John Deere 315 SE** hydraulic excavator.", "084518E", "Plant 235 Engr Regt, Akhnoor", "J&K", "77374876", 3, "084518E"),
        ],
        3,
    ),
    _lot(
        "08",
        "**Lot 8** at **Plant 102 Engr Regt, Leh** — **CAT D80 dozer** and **motor grader**. H1 **accepted** at ₹16.66 lakh.",
        [
            _eq("A", "CAT D80 crawler dozer", "Caterpillar **D80** track dozer at Leh.", "060588W", "Plant 102 Engr Regt, Leh", "Ladakh", "81458274", 3, "060588W"),
            _eq(
                "B", "Motor grader",
                "One **motor grader** — long-blade road levelling machine used in mountain road works.",
                "086087N", "Plant 102 Engr Regt, Leh", "Ladakh", "81458274", 3, "086087N — Motor Grader",
            ),
        ],
        3,
    ),
    _lot(
        "09",
        "**Lot 9** — **Kargil / Ladakh cluster**: three **JCB 3DX**, one **D80 dozer**, one **D50 dozer** "
        "across Drass, Achinathang, Handandrok, Kill PT, and Kargil locations.",
        [
            _eq("A", "JCB 3DX (Drass)", "JCB 3DX backhoe at Drass.", "084286E", "Plant 18 Engr Regt, Drass", "Ladakh", "94495686", 3, "084286E"),
            _eq("B", "JCB 3DX (Achinathang)", "JCB 3DX at Achinathang.", "084350E", "Plant 18 Engr Regt, Achinathang", "Ladakh", "94495686", 3, "084350E"),
            _eq("C", "CAT D50 dozer (Handandrok)", "CAT **D50** at Handandrok.", "070208A", "Plant, Handandrok", "Ladakh", "94495686", 3, "070208A"),
            _eq("D", "JCB 3DX (Kill PT)", "JCB 3DX at Kill PT.", "084333E", "Plant, Kill PT", "Ladakh", "94495686", 3, "084333E"),
            _eq("E", "CAT D80 dozer (Kargil)", "CAT **D80** at Kargil.", "060591W", "Plant, Kargil", "Ladakh", "94495686", 3, "060591W"),
        ],
        3,
    ),
    _lot(
        "10",
        "**Lot 10** — single **JCB 3DX** at **Plant 196 Fd Regt, Raiwala (Uttarakhand)**.",
        [
            _eq("A", "JCB 3DX backhoe loader", "One **JCB 3DX** backhoe loader.", "084302E", "Plant 196 Fd Regt, Raiwala", "Uttarakhand", "91939068", 3, "084302E"),
        ],
        3,
    ),
]

LOTS = ARCHIVE_34987

META = {
    "reference_no": "23 x Earth Moving Equipment Scrap — 10 Lots",
    "auction_date": "",
    "region": "Pan-India (PB, UP, J&K, Ladakh, UK)",
    "location_summary": "Army engineer regiments — Jalandhar, Leh, Mathura, Nyoma, Nagrota, Bareilly, Akhnoor, Kargil, Raiwala",
}
