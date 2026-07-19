"""Guards against silent GeM Live coverage regressions (xStatus bug)."""

from __future__ import annotations

import pytest

from scraper.config import GEM_FORWARD_LIVE_MIN_COUNT, GEM_FORWARD_STATUS_LIVE
from scraper.document_cache import safe_lot_dirname
from scraper.gem_forward_scraper import (
    GemForwardCoverageError,
    assert_live_coverage,
)


def test_live_status_is_homepage_live_not_subset() -> None:
    # Historical bug: xStatus=2 returned ~118 of ~500 Live auctions.
    assert GEM_FORWARD_STATUS_LIVE == "6"
    assert GEM_FORWARD_STATUS_LIVE != "2"
    assert GEM_FORWARD_LIVE_MIN_COUNT >= 250


def test_assert_live_coverage_passes_full_catalog() -> None:
    assert_live_coverage(497)
    assert_live_coverage(GEM_FORWARD_LIVE_MIN_COUNT)


def test_assert_live_coverage_fails_old_status2_counts() -> None:
    with pytest.raises(GemForwardCoverageError, match="xStatus"):
        assert_live_coverage(118)
    with pytest.raises(GemForwardCoverageError):
        assert_live_coverage(GEM_FORWARD_LIVE_MIN_COUNT - 1)


def test_safe_lot_dirname_sanitizes_decimal_lot_ids() -> None:
    assert safe_lot_dirname("4.0") == "4_0"
    assert safe_lot_dirname("1") == "1"
    assert safe_lot_dirname("") == "lot"
    assert "/" not in safe_lot_dirname("a/b")
