from __future__ import annotations

from typing import Any

# Structured lot catalogue from Tender_Document OCR — auction 31705
CATALOG_31705: list[dict[str, Any]] = [
    {
        "lot_code": "1A",
        "description": "Hand trolleys, fork lifters, battery trolleys, PP rope 30MT, steel wire rope 3MT",
        "location": "MO(V) Old Site",
        "flags": ["cpcb"],
        "lines": [
            {"sub_code": "A", "text": "Hand Trolley Assorted", "quantity": 5, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 25000},
            {"sub_code": "B", "text": "Fork Lifters Assorted", "quantity": 11, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 80000},
            {"sub_code": "C", "text": "Battery Operated Trolley", "quantity": 32, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 15000},
            {"sub_code": "D", "text": "Polypropylene Rope Scrap", "quantity": 30, "unit": "MT", "material_class": "polypropylene_rope", "quality_factor": 0.85, "evidence": {"page_image": "images/page-02.png", "page_no": 2}},
            {"sub_code": "E", "text": "Steel Wire Rope Scrap", "quantity": 3, "unit": "MT", "material_class": "steel_wire_rope", "evidence": {"page_image": "images/page-02.png", "page_no": 2}},
        ],
    },
    {
        "lot_code": "2A",
        "description": "Mixed IT/consumer electronics — 700 PCs, 500 TVs, printers, ACs, mattresses ×1000",
        "location": "MO(V) Old Site",
        "flags": ["cpcb", "ewaste"],
        "lines": [
            {"sub_code": "J", "text": "Computers / AIO", "quantity": 700, "unit": "nos", "material_class": "mixed_ewaste", "weight_kg_est": 10500, "quality_factor": 0.9},
            {"sub_code": "D", "text": "Television", "quantity": 500, "unit": "nos", "material_class": "mixed_ewaste", "weight_kg_est": 7500},
            {"sub_code": "K", "text": "Printers", "quantity": 100, "unit": "nos", "material_class": "mixed_ewaste", "weight_kg_est": 1500},
            {"sub_code": "M", "text": "Air Conditioners", "quantity": 50, "unit": "nos", "material_class": "mixed_ewaste", "weight_kg_est": 2500},
            {"sub_code": "Z", "text": "Foam/Coir Mattress", "quantity": 1000, "unit": "nos", "material_class": "mattress_disposal"},
            {"sub_code": "other", "text": "Other electronics (cameras, CCTV, fans, etc.)", "quantity": 1, "unit": "MT", "material_class": "mixed_ewaste", "quality_factor": 0.85},
        ],
    },
    {
        "lot_code": "3A",
        "description": "Bearing scrap 2.5MT, aluminium 1MT, brass, MT scrap, life rafts, chairs, mattresses ×2000",
        "location": "MO(V) Old Site",
        "flags": [],
        "lines": [
            {"sub_code": "A", "text": "Bearing Scrap", "quantity": 2.5, "unit": "MT", "material_class": "bearing_scrap"},
            {"sub_code": "B", "text": "Aluminium Scrap", "quantity": 1, "unit": "MT", "material_class": "aluminium"},
            {"sub_code": "D", "text": "Brass Boring Scrap", "quantity": 1, "unit": "MT", "material_class": "brass"},
            {"sub_code": "E", "text": "MT Scrap", "quantity": 1, "unit": "MT", "material_class": "hms_iron"},
            {"sub_code": "G", "text": "Life Rafts", "quantity": 30, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 5000},
            {"sub_code": "J", "text": "Mattress", "quantity": 2000, "unit": "nos", "material_class": "mattress_disposal"},
        ],
    },
    {
        "lot_code": "4A",
        "description": "Tyres assorted ×300",
        "location": "MO(V) Old Site",
        "flags": ["cpcb"],
        "lines": [
            {"sub_code": "A", "text": "Tyres Assorted", "quantity": 300, "unit": "nos", "material_class": "tyre_unit", "evidence": {"page_image": "images/page-03.png", "page_no": 3}},
        ],
    },
    {
        "lot_code": "5A",
        "description": "400KW Cummins diesel engine, 30T RT crane, 10T hydraulic crane, wood scrap 20MT",
        "location": "MO(V) Old Site",
        "flags": [],
        "lines": [
            {"sub_code": "A", "text": "400KW Mobile Diesel Engine (Cummins)", "quantity": 1, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 800000},
            {"sub_code": "B", "text": "RT 740B Crane 30 Ton", "quantity": 1, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 1200000},
            {"sub_code": "C", "text": "Hydraulic Mobile Crane 10 Ton", "quantity": 1, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 400000},
            {"sub_code": "D", "text": "Wood Scrap", "quantity": 20, "unit": "MT", "material_class": "wood_scrap"},
        ],
    },
    {
        "lot_code": "6A",
        "description": "Engines ×2, Genie lifts ×4",
        "location": "MO(V) Old Site",
        "flags": [],
        "lines": [
            {"sub_code": "A", "text": "Engine Assorted", "quantity": 2, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 150000},
            {"sub_code": "B", "text": "Genie Assorted", "quantity": 4, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 250000},
        ],
    },
    {
        "lot_code": "7A",
        "description": "Boats with engines ×3, motor boats ×2, OBM ×10",
        "location": "MO(V) Old Site",
        "flags": [],
        "lines": [
            {"sub_code": "A", "text": "Boat with engine", "quantity": 3, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 80000},
            {"sub_code": "B", "text": "Motor Boat (Scooter Boat)", "quantity": 2, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 60000},
            {"sub_code": "C", "text": "OBM Assorted", "quantity": 10, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 15000},
        ],
    },
    {
        "lot_code": "8A",
        "description": "HP air compressors ×13, pumps ×4, welding machines ×26, cupro-nickel 2MT, mattresses ×1000",
        "location": "MO(V) Old Site",
        "flags": [],
        "lines": [
            {"sub_code": "A", "text": "HP Air Compressor", "quantity": 13, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 40000},
            {"sub_code": "B", "text": "Submersible Pumps", "quantity": 4, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 20000},
            {"sub_code": "C", "text": "Welding Machines", "quantity": 26, "unit": "nos", "material_class": "industrial_equipment", "reuse_value_inr": 15000},
            {"sub_code": "D", "text": "Cupro Nickel", "quantity": 2, "unit": "MT", "material_class": "cupro_nickel"},
            {"sub_code": "E", "text": "Mattress", "quantity": 1000, "unit": "nos", "material_class": "mattress_disposal"},
        ],
    },
    {
        "lot_code": "9A",
        "description": "W/T Electrical Scrap 50 MT (CPCB)",
        "location": "MO(V) Old Site",
        "flags": ["cpcb", "ewaste"],
        "lines": [
            {"sub_code": "A", "text": "W/T Electrical Scrap", "quantity": 50, "unit": "MT", "material_class": "electrical_scrap", "evidence": {"page_image": "images/page-03.png", "page_no": 3}},
        ],
    },
]

CATALOGS: dict[str, list[dict[str, Any]]] = {
    "31705": CATALOG_31705,
}


def get_catalog(auction_id: str) -> list[dict[str, Any]]:
    return CATALOGS.get(auction_id, [])
