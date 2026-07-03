from scraper.category_map import (
    normalize_eauction_category,
    normalize_gem_category,
    normalize_mstc_category,
    should_exclude_category,
)


def test_mstc_scrap_category():
    assert normalize_mstc_category(category="Metal Scrap", lot_title="Iron scrap lot") == "scrap"


def test_gem_machinery_category():
    assert normalize_gem_category(category="Industrial", sub_category="Machinery") == "machinery"


def test_eauction_coal_category():
    assert normalize_eauction_category(product_category="Minerals", sub_category="Coal") == "coal"


def test_exclude_property_for_non_mstc():
    assert should_exclude_category("property", source="eauction") is True
    assert should_exclude_category("property", source="mstc") is False


def test_other_fallback():
    assert normalize_mstc_category(lot_title="Miscellaneous items") == "other"
