from __future__ import annotations

from typing import Any

from scraper.gem_analysis.constants import (
    DEFAULT_DISTANCE_KM,
    GEM_FEE_RATE,
    GST_FLOAT_DAYS,
    GST_RCM_RATE,
    ITC_RECOVERY,
    LOADING_PER_MT,
    MARKET_RATES,
    NAVAL_SITE_FACTOR,
    TRANSPORT_PER_MT_KM,
    VERDICT_THRESHOLDS,
)


def _verdict(margin_pct: float) -> str:
    for threshold, label in VERDICT_THRESHOLDS:
        if margin_pct > threshold:
            return label
    return "STRONG LOSS"


def _rate(material: str, scenario: str) -> float:
    band = MARKET_RATES.get(material, MARKET_RATES["hms_iron"])
    return float(band[scenario])


def _gross_line(line: dict[str, Any], scenario: str) -> float:
    mat = line.get("material_class", "hms_iron")
    qty = line.get("quantity") or 0
    unit = line.get("unit", "")
    qf = line.get("quality_factor", 1.0)
    if scenario == "best":
        qf = min(1.0, qf + 0.1)
        rate_key = "high"
    elif scenario == "worst":
        qf = max(0.5, qf - 0.15)
        rate_key = "low"
    else:
        rate_key = "mid"

    if unit == "MT":
        kg = qty * 1000
    elif unit == "kg":
        kg = qty
    elif unit == "nos":
        if mat == "tyre_unit":
            return qty * _rate("tyre_unit", rate_key) * qf
        reuse = line.get("reuse_value_inr")
        if reuse:
            mult = {"best": 1.15, "base": 1.0, "worst": 0.85}[scenario]
            return reuse * mult
        return qty * 5000 * qf  # generic unit fallback
    else:
        kg = line.get("weight_kg_est") or 0

    rate = _rate(mat, rate_key)
    return kg * rate * qf


def _compliance_pct(lot: dict[str, Any]) -> float:
    flags = lot.get("flags") or []
    if "cpcb" in flags and "ewaste" in flags:
        return 0.22
    if "cpcb" in flags:
        return 0.18
    return 0.0


def _disposal_inr(lines: list[dict[str, Any]]) -> float:
    total = 0.0
    for ln in lines:
        if ln.get("material_class") == "mattress_disposal":
            total += (ln.get("quantity") or 0) * 75
    return total


def value_lot(lot: dict[str, Any], scenario: str = "base") -> dict[str, Any]:
    lines = lot.get("lines") or []
    weight_mt = sum(
        (ln.get("quantity") or 0 if ln.get("unit") == "MT" else (ln.get("weight_kg_est") or 0) / 1000)
        for ln in lines
        if ln.get("unit") in ("MT", "kg") or ln.get("weight_kg_est")
    )
    for ln in lines:
        if ln.get("unit") == "kg":
            weight_mt += (ln.get("quantity") or 0) / 1000

    gross = sum(_gross_line(ln, scenario) for ln in lines)
    h1 = lot.get("h1_inr") or 0
    site_factor = NAVAL_SITE_FACTOR if "naval" in (lot.get("location") or "").lower() or "MO(V)" in (lot.get("location") or "") else 1.0
    cost_mult = {"best": 0.9, "base": 1.0, "worst": 1.15}[scenario]

    loading = weight_mt * LOADING_PER_MT * site_factor * cost_mult
    transport = weight_mt * DEFAULT_DISTANCE_KM * TRANSPORT_PER_MT_KM * cost_mult
    compliance = gross * _compliance_pct(lot) * cost_mult
    disposal = _disposal_inr(lines) * cost_mult
    gem_fee = h1 * GEM_FEE_RATE
    tax_float = h1 * GST_RCM_RATE * (GST_FLOAT_DAYS / 365) * (1 - ITC_RECOVERY)

    total_costs = h1 + loading + transport + compliance + disposal + gem_fee + tax_float
    net = gross - total_costs
    margin_pct = (net / h1 * 100) if h1 else 0.0

    formulas = [
        {"label": "Gross resale", "amount_inr": gross, "formula": f"Σ qty × rate ({scenario})"},
        {"label": "H1 purchase", "amount_inr": -h1, "formula": "GeM winning bid"},
        {
            "label": "Loading",
            "amount_inr": -loading,
            "formula": f"{weight_mt:.1f} MT × ₹{LOADING_PER_MT} × {site_factor}",
        },
        {
            "label": "Transport",
            "amount_inr": -transport,
            "formula": f"{weight_mt:.1f} MT × {DEFAULT_DISTANCE_KM} km × ₹{TRANSPORT_PER_MT_KM}",
        },
        {"label": "CPCB / compliance", "amount_inr": -compliance, "formula": f"{_compliance_pct(lot)*100:.0f}% of gross"},
        {"label": "Disposal", "amount_inr": -disposal, "formula": "Mattress / waste units"},
        {"label": "GeM fee", "amount_inr": -gem_fee, "formula": f"H1 × {GEM_FEE_RATE*100:.1f}%"},
        {"label": "GST float", "amount_inr": -tax_float, "formula": f"RCM {GST_RCM_RATE*100:.0f}% × {GST_FLOAT_DAYS}d"},
    ]

    return {
        "gross_inr": round(gross, 2),
        "total_costs_inr": round(total_costs, 2),
        "net_profit_inr": round(net, 2),
        "margin_pct": round(margin_pct, 2),
        "verdict": _verdict(margin_pct),
        "formulas": formulas,
        "loading_inr": round(loading, 2),
        "transport_inr": round(transport, 2),
        "compliance_inr": round(compliance, 2),
        "disposal_inr": round(disposal, 2),
        "gem_fee_inr": round(gem_fee, 2),
        "tax_float_inr": round(tax_float, 2),
    }


def value_auction(lots: list[dict[str, Any]]) -> dict[str, Any]:
    scenarios: dict[str, Any] = {}
    for sc in ("best", "base", "worst"):
        gross = sum(value_lot(lot, sc)["gross_inr"] for lot in lots)
        net = sum(value_lot(lot, sc)["net_profit_inr"] for lot in lots)
        h1 = sum(lot.get("h1_inr") or 0 for lot in lots)
        scenarios[sc] = {
            "gross_resale_inr": round(gross, 2),
            "net_profit_inr": round(net, 2),
            "margin_pct": round(net / h1 * 100, 2) if h1 else 0,
            "verdict": _verdict(net / h1 * 100 if h1 else 0),
        }
    return scenarios
