from __future__ import annotations

from datetime import date

# Vizag-region scrap rates (INR/kg) — Jun 2026 research snapshot
MARKET_RATES = {
    "hms_iron": {"low": 29, "mid": 33, "high": 36},
    "machinery_scrap": {"low": 24, "mid": 28, "high": 32},
    "steel_wire_rope": {"low": 28, "mid": 32, "high": 35},
    "polypropylene_rope": {"low": 8, "mid": 12, "high": 18},
    "aluminium": {"low": 140, "mid": 152, "high": 165},
    "brass": {"low": 380, "mid": 410, "high": 430},
    "cupro_nickel": {"low": 280, "mid": 350, "high": 450},
    "bearing_scrap": {"low": 26, "mid": 30, "high": 34},
    "mixed_ewaste": {"low": 35, "mid": 45, "high": 55},
    "electrical_scrap": {"low": 38, "mid": 48, "high": 58},
    "wood_scrap": {"low": 4, "mid": 7, "high": 10},
    "tyre_scrap": {"low": 8, "mid": 15, "high": 25},  # per kg est
    "tyre_unit": {"low": 120, "mid": 200, "high": 350},  # per tyre
    "boat_scrap": {"low": 25, "mid": 35, "high": 50},
    "industrial_equipment": {"low": 40, "mid": 80, "high": 150},  # per kg for cranes etc.
}

RESEARCH_CITATIONS = [
    {
        "material_class": "hms_iron",
        "url": "https://scraprates.in/visakhapatnam",
        "accessed": str(date.today()),
        "snippet": "Iron ~₹32.93/kg Visakhapatnam",
    },
    {
        "material_class": "mixed_ewaste",
        "url": "https://scraprates.in/gurgaon/e-waste-scrap-price",
        "accessed": str(date.today()),
        "snippet": "Mixed e-waste ~₹45/kg",
    },
    {
        "material_class": "lead_acid_battery",
        "url": "https://scraprates.in/scrap-materials/lead-acid-battery",
        "accessed": str(date.today()),
        "snippet": "Lead-acid battery ~₹66-71/kg India",
    },
]

VERDICT_THRESHOLDS = (
    (15, "STRONG PROFIT"),
    (5, "PROFIT"),
    (-5, "MARGINAL"),
    (-20, "LOSS"),
    (-999, "STRONG LOSS"),
)

GEM_FEE_RATE = 0.015
GST_RCM_RATE = 0.18
GST_FLOAT_DAYS = 45
ITC_RECOVERY = 1.0
LOADING_PER_MT = 700
TRANSPORT_PER_MT_KM = 30
DEFAULT_DISTANCE_KM = 35
NAVAL_SITE_FACTOR = 1.2
