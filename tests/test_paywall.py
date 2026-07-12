"""Paywall plan and entitlement tests (Anvil Phase 005, Pass 2)."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLANS_TS = REPO / "web" / "src" / "lib" / "plans.ts"
ENTITLEMENTS_TS = REPO / "web" / "src" / "lib" / "entitlements.ts"
CHECKOUT_TS = REPO / "web" / "src" / "lib" / "checkout.ts"
ANALYTICS_TS = REPO / "web" / "src" / "lib" / "analytics.ts"
PACKAGE_JSON = REPO / "web" / "package.json"


def _parse_plan_caps(src: str) -> dict[str, dict[str, int]]:
    caps: dict[str, dict[str, int]] = {}
    for plan in ("free", "pro", "trader", "team", "enterprise"):
        m = re.search(
            rf"{plan}:\s*\{{\s*watchlist:\s*(\d+(?:_\d+)?),\s*savedSearches:\s*(\d+(?:_\d+)?)",
            src,
        )
        assert m, f"missing PLAN_CAPS entry for {plan}"
        caps[plan] = {
            "watchlist": int(m.group(1).replace("_", "")),
            "savedSearches": int(m.group(2).replace("_", "")),
        }
    return caps


def _parse_entitlement_block(src: str, block_name: str) -> tuple[list[str], list[str]]:
    m = re.search(rf"const {block_name}[^=]*=\s*\[([\s\S]*?)\];", src)
    assert m, f"missing {block_name}"
    body = m.group(1)
    direct = re.findall(r"ENTITLEMENTS\.(\w+)", body)
    spreads = re.findall(r"\.\.\.(\w+)", body)
    return direct, spreads


def test_plan_catalog_covers_all_tiers():
    src = PLANS_TS.read_text(encoding="utf-8")
    for plan in ("free", "pro", "trader", "team", "enterprise"):
        assert f'"{plan}"' in src
    assert "PLAN_CAPS" in src
    assert "ENTITLEMENTS" in src


def test_free_caps_exact():
    caps = _parse_plan_caps(PLANS_TS.read_text(encoding="utf-8"))
    assert caps["free"]["watchlist"] == 5
    assert caps["free"]["savedSearches"] == 2


def test_plan_caps_monotonic():
    caps = _parse_plan_caps(PLANS_TS.read_text(encoding="utf-8"))
    order = ["free", "pro", "trader", "team", "enterprise"]
    for i in range(1, len(order)):
        prev, cur = order[i - 1], order[i]
        assert caps[cur]["watchlist"] >= caps[prev]["watchlist"]
        assert caps[cur]["savedSearches"] >= caps[prev]["savedSearches"]


def test_plan_entitlement_hierarchy_monotonic():
    src = PLANS_TS.read_text(encoding="utf-8")
    trader_direct, trader_spreads = _parse_entitlement_block(src, "TRADER_ENTITLEMENTS")
    team_direct, team_spreads = _parse_entitlement_block(src, "TEAM_ENTITLEMENTS")
    _, enterprise_spreads = _parse_entitlement_block(src, "ENTERPRISE_ENTITLEMENTS")
    assert "PRO_ENTITLEMENTS" in trader_spreads
    assert "TRADER_ENTITLEMENTS" in team_spreads
    assert "TEAM_ENTITLEMENTS" in enterprise_spreads
    assert "ADVANCED_DILIGENCE" in trader_direct
    assert "ALERTS" in trader_direct


def test_minimum_plan_mapping_covers_premium_features():
    src = ENTITLEMENTS_TS.read_text(encoding="utf-8")
    for feature in (
        "watchlist_add",
        "saved_search_save",
        "filter_geo_radius",
        "diligence_advanced",
        "whatsapp_alert",
        "ai_deep_summary",
    ):
        assert feature in src
        assert "minimumPlan:" in src


def test_entitlement_helpers_present():
    src = ENTITLEMENTS_TS.read_text(encoding="utf-8")
    for fn in (
        "getCurrentPlan",
        "hasEntitlement",
        "canAddWatchlist",
        "canSaveSearch",
        "canUsePremiumFeature",
        "loadDemoPlanOverride",
    ):
        assert f"function {fn}" in src


def test_demo_plan_requires_explicit_env():
    src = ENTITLEMENTS_TS.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_PAYWALL_DEMO_MODE" in src
    assert "mstc_paywall_demo_plan_v1" in src


def test_checkout_stub_disabled_without_config():
    src = CHECKOUT_TS.read_text(encoding="utf-8")
    assert "isBillingConfigured" in src
    assert "not_configured" in src
    assert "not_implemented" in src
    assert "return { ok: true" not in src
    assert "@stripe" not in src
    assert "razorpay" not in src.lower()


def test_no_payment_sdk_packages():
    import json

    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    forbidden = {"stripe", "razorpay", "@stripe/stripe-js", "@razorpay/checkout"}
    assert forbidden.isdisjoint(deps.keys())


def test_paywall_analytics_events():
    src = ANALYTICS_TS.read_text(encoding="utf-8")
    for event in (
        "pricing_page_view",
        "plan_select",
        "upgrade_prompt_view",
        "upgrade_cta_click",
        "gated_feature_attempt",
        "checkout_start_stub",
        "enterprise_inquiry_click",
        "account_page_view",
        "saved_search_save",
    ):
        assert f'"{event}"' in src


def test_paywall_runbook_exists():
    runbook = REPO / "docs" / "PAYWALL_RUNBOOK.md"
    assert runbook.is_file()
    body = runbook.read_text(encoding="utf-8")
    assert "SEO" in body
    assert "entitlement" in body.lower()
    assert "billing" in body.lower()
    assert "buyer validation" in body.lower()
    assert "Razorpay" in body or "Stripe" in body


def test_release_checklist_mentions_paywall():
    checklist = REPO / "docs" / "RELEASE_CHECKLIST.md"
    body = checklist.read_text(encoding="utf-8")
    assert "paywall" in body.lower() or "PAYWALL" in body
    assert "legal review" in body.lower()
    assert "buyer validation" in body.lower()
