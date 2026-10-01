"""Descriptive changes, with no financial-quality or investment approval."""
from decimal import Decimal


def reported_change(prior: Decimal, current: Decimal) -> dict:
    if not prior.is_finite() or not current.is_finite():
        raise ValueError("reported trend values must be finite")
    change = current - prior
    return {
        "prior_cny": str(prior), "current_cny": str(current), "change_cny": str(change),
        "growth_rate": str(change / prior) if prior > 0 else None,
        "growth_status": "CALCULATED" if prior > 0 else "NOT_ASSESSABLE_NONPOSITIVE_BASE",
        "direction": "UP" if change > 0 else "DOWN" if change < 0 else "UNCHANGED",
    }
