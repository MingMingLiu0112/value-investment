"""Quantify how a conditional owner-cash path depends on assumed borrowing.

Each annual counterfactual holds that year's opening state fixed. It is not a
multi-year no-refinancing valuation or evidence that credit is available.
"""

from decimal import Decimal


def _amount(row, key):
    value = Decimal(row[key])
    if not value.is_finite():
        raise ValueError("PARENT_FINANCING_NONFINITE_ANNUAL_VALUE:" + key)
    return value


def assess_parent_financing_dependency(compiled, bridge=None):
    """Consume the shared model's annual ledger without changing its receipt."""
    if compiled.get("action") != "no_order" or not compiled.get("valuation_date"):
        raise ValueError("PARENT_FINANCING_UNBOUND_MODEL_RESULT")
    if bridge is not None and (bridge.get("symbol") != compiled.get("symbol")
            or bridge.get("period_start") != compiled["valuation_date"]
            or bridge.get("complete_debt_scope_verified") is not False):
        raise ValueError("PARENT_FINANCING_FOLLOWUP_CANNOT_REBASE_MODEL")
    scenarios = {}
    for name in ("bear", "base", "bull"):
        rows = compiled["scenarios"][name]["calculation"]["annual_rows"]
        if not rows:
            raise ValueError("PARENT_FINANCING_ANNUAL_LEDGER_REQUIRED")
        annual = []
        for row in rows:
            policy = row["cash_policy"]
            borrowing = _amount(policy, "new_borrowing")
            floor = _amount(policy, "cash_floor")
            before = _amount(row, "cash_before_distribution_cny")
            distribution = _amount(row, "conditional_distribution_cny")
            if borrowing < 0 or distribution < 0 or before < floor + distribution:
                raise ValueError("PARENT_FINANCING_ANNUAL_LEDGER_INCONSISTENT")
            without = before - borrowing
            needed_floor = max(Decimal(0), floor - without)
            needed_distribution = max(Decimal(0), floor + distribution - without)
            annual.append(dict(year=row["year"], assumed_new_borrowing_cny=str(borrowing),
                cash_before_distribution_without_this_year_borrowing_cny=str(without),
                minimum_borrowing_to_preserve_cash_floor_cny=str(needed_floor),
                minimum_borrowing_to_preserve_modeled_distribution_cny=str(needed_distribution),
                modeled_distribution_cny=str(distribution),
                assumption_dependent=needed_distribution > 0))
        scenarios[name] = annual
    return dict(schema_version="parent-financing-dependency-v1", symbol=compiled["symbol"],
        valuation_date=compiled["valuation_date"], action="no_order",
        scope="ANNUAL_SINGLE_YEAR_COUNTERFACTUAL_HOLDING_MODELED_OPENING_STATE",
        actual_refinancing_capacity_verified=False,
        main_valuation_recomputed=False, scenarios=scenarios,
        followup_observation_date=bridge["period_end"] if bridge else None,
        followup_rebases_historical_valuation=False)
