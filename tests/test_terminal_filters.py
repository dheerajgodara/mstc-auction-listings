from __future__ import annotations

import re


def parse_emd_inr(emd_summary: str | None) -> float | None:
    if not emd_summary:
        return None
    m = re.search(r"₹?\s*([\d.]+)", emd_summary.replace(",", ""))
    if not m:
        return None
    n = float(m.group(1))
    if "lakh" in emd_summary.lower():
        n *= 100000
    return n


def emd_eligible(required: float | None, balance: float) -> bool:
    if required is None:
        return True
    if balance <= 0:
        return False
    return balance >= required


def lots_coverable(emd_per_lot: float, balance: float) -> int:
    if emd_per_lot <= 0 or balance <= 0:
        return 0
    return int(balance // emd_per_lot)


def test_parse_emd_lakh():
    assert parse_emd_inr("₹1.5 Lakh") == 150000


def test_emd_eligible():
    assert emd_eligible(50000, 100000) is True
    assert emd_eligible(150000, 100000) is False


def test_lots_coverable():
    assert lots_coverable(50000, 200000) == 4


def test_haversine_delhi_jaipur():
    from math import atan2, cos, radians, sin, sqrt

    def haversine(lat1, lng1, lat2, lng2):
        r = 6371
        d_lat = radians(lat2 - lat1)
        d_lng = radians(lng2 - lng1)
        a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
        return r * 2 * atan2(sqrt(a), sqrt(1 - a))

    d = haversine(28.6139, 77.209, 26.9124, 75.7873)
    assert 200 < d < 280
