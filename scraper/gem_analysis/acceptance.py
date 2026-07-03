from __future__ import annotations

PRIORS = {
    "Accepted": 0.95,
    "Pending Transaction Charge Payment": 0.425,
    "Rejected": 0.05,
}


def p_success(status: str, flags: list[str] | None = None) -> float:
    base = PRIORS.get(status, 0.47)
    if flags and "cpcb" in flags:
        base *= 0.92
    return round(base * 100, 1)
