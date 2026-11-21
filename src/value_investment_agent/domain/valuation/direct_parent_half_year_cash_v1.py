"""Date the direct-owner cash ledger after an explicit June close."""

from datetime import date, datetime, timezone
from decimal import Decimal, localcontext

from .direct_parent_owner_cash_v2 import compile_direct_owner_cash_path
from .parent_cash_policy import _number
from ...valuation_models.residual_income import valuation_time_factor


def value_parent_half_year_cash(
    *, valuation_date: date, first_period_start: date, first_period_end: date,
    minimum_distribution_by_year: dict[int, str] | None = None, **cash_inputs,
) -> dict:
    """Consume explicit H2 stub flows and subsequent complete fiscal years.

    The caller must supply balances as of June 30 and only July–December
    amounts in the first row. Terminal economics and cash constraints are
    checked by the existing owner-cash model before applying dated discounts.
    """
    if type(valuation_date) is not date or (valuation_date.month, valuation_date.day) != (6, 30):
        raise ValueError("DIRECT_OWNER_H1_VALUATION_DATE_REQUIRED")
    if (type(first_period_start) is not date or type(first_period_end) is not date
            or first_period_start != date(valuation_date.year, 7, 1)
            or first_period_end != date(valuation_date.year, 12, 31)):
        raise ValueError("DIRECT_OWNER_H2_EXPLICIT_STUB_PERIOD_REQUIRED")
    years = cash_inputs["years"]
    if not years or years[0].get("year") != valuation_date.year:
        raise ValueError("DIRECT_OWNER_H2_STUB_YEAR_REQUIRED")
    calculation = compile_direct_owner_cash_path(**cash_inputs)
    floor_inputs = {} if minimum_distribution_by_year is None else minimum_distribution_by_year
    fiscal_years = {row["year"] for row in calculation["annual_rows"]}
    if not isinstance(floor_inputs, dict) or any(
        type(year) is not int or year not in fiscal_years for year in floor_inputs
    ):
        raise ValueError("DIRECT_OWNER_H2_DISTRIBUTION_FLOOR_YEARS_INVALID")
    floors = {year: _number(amount) for year, amount in floor_inputs.items()}
    if any(amount < 0 for amount in floors.values()):
        raise ValueError("DIRECT_OWNER_H2_NEGATIVE_DISTRIBUTION_FLOOR")
    for row in calculation["annual_rows"]:
        year = row["year"]
        if year in floors and _number(row["total_owner_distribution_cny"]) < floors[year]:
            raise ValueError(f"DIRECT_OWNER_H2_DISTRIBUTION_BELOW_DECLARED_FLOOR:{year}")
    cost = _number(cash_inputs["cost_of_equity"])
    year = valuation_date.year
    with localcontext() as context:
        context.prec = 48
        elapsed, _ = valuation_time_factor(
            cost, datetime(year - 1, 12, 31, tzinfo=timezone.utc),
            datetime(year, 6, 30, tzinfo=timezone.utc))
        stub = Decimal(1) - elapsed
        rows = []
        owner_pv = Decimal(0)
        residual_pv = Decimal(calculation["annual_rows"][0]["opening_book_equity_cny"])
        for index, annual in enumerate(calculation["annual_rows"]):
            term = stub if index == 0 else Decimal(1)
            payment_time = stub + index
            divisor = (1 + cost) ** payment_time
            capital_charge = Decimal(annual["opening_book_equity_cny"]) * ((1 + cost) ** term - 1)
            residual = Decimal(annual["net_income_assumption_cny"]) - capital_charge
            owner_pv += Decimal(annual["total_owner_distribution_cny"]) / divisor
            residual_pv += residual / divisor
            rows.append(dict(annual, payment_date=date(year + index, 12, 31).isoformat(),
                             discount_years=str(payment_time), equity_charge_cny=str(capital_charge),
                             residual_income_cny=str(residual)))
        terminal = Decimal(calculation["terminal_equity_value_cny"])
        closing_book = Decimal(rows[-1]["closing_book_equity_cny"])
        equity = owner_pv + terminal / divisor
        ri = residual_pv + (terminal - closing_book) / divisor
        if abs(ri - equity) > max(Decimal("0.00000001"), abs(equity) * Decimal("1e-36")):
            raise ValueError("DIRECT_OWNER_H2_RI_DISTRIBUTION_CROSSCHECK_FAILED")
        return dict(calculation, schema_version="direct-parent-half-year-cash-v1",
                    valuation_date=valuation_date.isoformat(), first_period_start=first_period_start.isoformat(),
                    first_period_end=first_period_end.isoformat(), annual_rows=rows,
                    terminal_value_date=rows[-1]["payment_date"],
                    minimum_distribution_by_year={k: str(v) for k, v in floors.items()},
                    conditional_equity_value_cny=str(equity),
                    per_share_value=str(equity / _number(cash_inputs["ordinary_shares"])),
                    dividend_crosscheck_equity_value_cny=str(equity),
                    residual_income_equity_value_cny=str(ri),
                    crosscheck_difference_cny=str(ri - equity))
