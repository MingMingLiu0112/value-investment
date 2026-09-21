"""Bounded one-variable reverse valuation, for explanation rather than fitting."""
from __future__ import annotations

from decimal import Decimal
from typing import Callable


def solve_bounded_monotonic(*, target: Decimal, lower: Decimal, upper: Decimal,
                            value_at: Callable[[Decimal], Decimal]) -> dict[str, str | None]:
    """Solve only inside a registered range; return no-solution outside it."""
    if not all(value.is_finite() for value in (target, lower, upper)) or target <= 0 or lower >= upper:
        raise ValueError("Target and ordered finite bounds are required")
    lo_value, hi_value = value_at(lower), value_at(upper)
    if not all(value.is_finite() and value > 0 for value in (lo_value, hi_value)) or lo_value >= hi_value:
        raise ValueError("Value function must be positive and strictly increasing on bounds")
    result = {"target": str(target), "bounds": [str(lower), str(upper)],
              "value_bounds": [str(lo_value), str(hi_value)], "solution": None}
    if target < lo_value:
        return {**result, "status": "below_registered_envelope"}
    if target > hi_value:
        return {**result, "status": "above_registered_envelope"}
    for _ in range(100):
        middle = (lower + upper) / Decimal(2)
        value = value_at(middle)
        if not value.is_finite() or value < lo_value or value > hi_value:
            raise ValueError("Value function is not monotonic within registered bounds")
        if abs(value - target) <= Decimal("0.000001"):
            return {**result, "status": "conditional_solution", "solution": str(middle), "repriced_value": str(value)}
        if value < target:
            lower = middle
        else:
            upper = middle
    raise ValueError("Reverse valuation did not converge")
