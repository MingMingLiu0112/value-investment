"""Derive an observed calendar Q4 from explicitly bound FY and nine-month facts."""

from copy import deepcopy
from datetime import date
from decimal import localcontext

from . import period_earnings_assembly_v1 as periods


def derive_actual_fourth_quarter(*, full_year, nine_months, asof):
    """Keep source operands and reject forecasts or mismatched calendar years."""
    start, end, full = periods._segment(full_year, asof)
    start9, end9, nine = periods._segment(nine_months, asof)
    year = start.year
    if (full_year["kind"] == "FORECAST_ASSUMPTION"
            or nine_months["kind"] == "FORECAST_ASSUMPTION"
            or start != date(year, 1, 1) or start9 != start
            or end != date(year, 12, 31) or end9 != date(year, 9, 30)):
        raise ValueError("SAME_YEAR_ACTUAL_FY_AND_9M_REQUIRED")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        amounts = [str(a - b) for a, b in zip(full, nine, strict=True)]
    parent = periods._parent(*amounts)
    return dict(
        period_start=f"{year}-10-01", period_end=end.isoformat(),
        kind="DERIVED_FACT", currency="CNY", scope="consolidated",
        **dict(zip(periods.AMOUNTS, amounts, strict=True)),
        parent_profit_cny=parent["parent_profit_cny"],
        source_refs=periods._merge_refs([full_year, nine_months], "source_refs"),
        assumption_refs=[], asof=periods._stamp(asof).isoformat(),
        derivation=dict(version="actual-fiscal-fourth-quarter-v1", formula="same_year_fy_minus_9m",
                        operands=deepcopy([full_year, nine_months])),
    )
