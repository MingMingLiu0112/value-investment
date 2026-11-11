"""Fiscal-year policy diagnostics, separate from legal capacity and cash payment."""
from decimal import Decimal, localcontext
from ..valuation.signed_parent_profit import _number

VERSION = "fiscal-distribution-policy-review-v1"

def evaluate_fiscal_distribution_policy(*, policy, reported_half, forecast_half):
    """Fiscal H1 facts + H2 assumptions; never compare a rolling year to a FY floor."""
    if (not isinstance(policy, dict) or set(policy) != {
            "fiscal_year", "minimum_payout_ratio", "minimum_distribution_cny", "currency", "scope"}
            or type(policy["fiscal_year"]) is not int or not 1900 <= policy["fiscal_year"] <= 2200
            or policy["currency"] != "CNY" or policy["scope"] != "consolidated_parent"):
        raise ValueError("EXPLICIT_FISCAL_PARENT_POLICY_REQUIRED")
    year = policy["fiscal_year"]
    for row, start, end, kind in (
        (reported_half, f"{year}-01-01", f"{year}-06-30", "REPORTED_FACT"),
        (forecast_half, f"{year}-07-01", f"{year}-12-31", "FORECAST_ASSUMPTION"),
    ):
        if (not isinstance(row, dict) or set(row) != {
                "period_start", "period_end", "parent_profit_cny", "currency", "scope", "kind"}
                or row["period_start"] != start or row["period_end"] != end
                or row["currency"] != "CNY" or row["scope"] != "consolidated_parent" or row["kind"] != kind):
            raise ValueError("SAME_FISCAL_YEAR_EXACT_HALF_PERIODS_REQUIRED")
    with localcontext() as ctx:
        ctx.prec = 48
        ratio = _number(policy["minimum_payout_ratio"])
        floor = _number(policy["minimum_distribution_cny"])
        if not 0 <= ratio <= 1 or floor < 0:
            raise ValueError("INVALID_DISCLOSED_POLICY_BOUNDS")
        actual = _number(reported_half["parent_profit_cny"])
        assumed = _number(forecast_half["parent_profit_cny"])
        profit = actual + assumed
        proportional = max(profit, Decimal(0)) * ratio
        target = max(floor, proportional)
        excess = max(target - max(profit, Decimal(0)), Decimal(0))
        return dict(schema_version=VERSION, action="no_order",
            status="CONDITIONAL_FISCAL_POLICY_DIAGNOSTIC", fiscal_year=year,
            reported_h1_parent_profit_cny=str(actual), assumed_h2_parent_profit_cny=str(assumed),
            conditional_fy_parent_profit_cny=str(profit), ratio_target_cny=str(proportional),
            disclosed_floor_cny=str(floor), policy_target_cny=str(target),
            target_above_current_year_positive_earnings_cny=str(excess),
            dominant_constraint="ABSOLUTE_FLOOR" if floor >= proportional else "PAYOUT_RATIO",
            funding_status="NOT_ASSESSED", payment_status="NOT_ASSESSED",
            policy_compliance="NOT_ASSESSED", formal_eligibility=False,
            main_range_adopted=False, condition_price=None,
            limitations=[
                "Target above earnings is not a cash deficit or proof of noncompliance; retained earnings and accessible cash require separate verification.",
                "Policy is conditional intention, not a declared liability, paid dividend or perpetual terminal guarantee.",
                "Fiscal attribution, declaration date and payment date differ; prior-year payments do not satisfy this fiscal-year target.",
                "No rolling-year ledger, historical valuation or approval is rewritten."])


def compare_fiscal_projection_with_nine_months(*, fiscal_review, ytd_update):
    """Show the Q4 required by an unchanged conditional FY projection.

    A negative implied Q4 is a research implication, not a reported loss or an
    automatic rejection. New actuals never overwrite the frozen projection.
    """
    if (not isinstance(fiscal_review, dict) or not isinstance(ytd_update, dict)
            or fiscal_review.get("status") != "CONDITIONAL_FISCAL_POLICY_DIAGNOSTIC"
            or ytd_update.get("status") != "VERIFIED"
            or ytd_update.get("period_basis") != "YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER"):
        raise ValueError("VERIFIED_NINE_MONTHS_AND_CONDITIONAL_FISCAL_PATH_REQUIRED")
    year = fiscal_review["fiscal_year"]
    if type(year) is not int or not 1900 <= year <= 2200:
        raise ValueError("EXACT_FISCAL_YEAR_REQUIRED")
    if (ytd_update.get("period_start") != f"{year}-01-01"
            or ytd_update.get("period_end") != f"{year}-09-30"):
        raise ValueError("SAME_FISCAL_YEAR_NINE_MONTHS_REQUIRED")
    anchor = ytd_update["fields"]["parent_profit_cny"]
    if anchor.get("scope") != "consolidated_parent" or anchor.get("unit") != "CNY":
        raise ValueError("NINE_MONTH_PARENT_CNY_SCOPE_REQUIRED")
    with localcontext() as ctx:
        ctx.prec = 48
        projected = _number(fiscal_review["conditional_fy_parent_profit_cny"])
        actual = _number(anchor["value"])
        remaining = projected - actual
    return dict(status="ACTUAL_UPDATE_COMPARED_WITH_FROZEN_CONDITIONAL_PATH",
        fiscal_year=year, reported_ytd_parent_profit_cny=str(actual),
        unchanged_conditional_fy_parent_profit_cny=str(projected),
        implied_q4_parent_profit_cny=str(remaining),
        implied_q4_start=f"{year}-10-01", implied_q4_end=f"{year}-12-31",
        implication="IMPLIED_Q4_LOSS_REQUIRES_EXPLICIT_REVIEW" if remaining < 0 else "IMPLIED_Q4_PROFIT_REQUIRES_EXPLICIT_REVIEW",
        value_classification="DERIVED_CONDITIONAL_IMPLICATION_NOT_REPORTED_Q4_OR_NEW_FORECAST",
        source_anchor=anchor, model_revalidated=False, formal_eligibility=False,
        action="no_order", condition_price=None)
