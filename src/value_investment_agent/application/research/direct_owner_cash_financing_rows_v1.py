"""Opt-in annual financing detail for source-bound parent cash revisions."""

from dataclasses import replace
from decimal import Decimal
import json

from .direct_owner_cash_compilation_v2 import financing_maturity_floor
from .direct_owner_cash_staged_v3 import staged_parent_cash_request_v3


def annual_financing_row_v1(*, year: int, closing_debt_cny: str,
                            debt_repayment_cny: str, interest_outside_cfo_cny: str,
                            disclosed_unsettled_maturities_cny: Decimal | str) -> dict:
    """Split a sealed year's gross repayment using its verified outstanding maturity floor."""
    scheduled = Decimal(disclosed_unsettled_maturities_cny)
    if not scheduled.is_finite() or scheduled < 0:
        raise ValueError("DIRECT_INPUT_FINANCING_CONSTRAINT_INVALID")
    remainder = Decimal(debt_repayment_cny) - scheduled
    if remainder < 0:
        raise ValueError(f"PARENT_V3_REPAYMENT_BELOW_CONTRACTUAL_FLOOR:{year}")
    return dict(year=year, closing_debt_cny=closing_debt_cny,
                disclosed_unsettled_maturities_cny=str(scheduled),
                other_forecast_principal_payments_cny=str(remainder),
                forecast_interest_outside_cfo_cny=interest_outside_cfo_cny,
                undated_outstanding_principal_cny=None)


def staged_financing_request_v1(**kwargs):
    """Add annual financing rows only to an explicitly requested financing revision."""
    request = staged_parent_cash_request_v3(**kwargs)
    if kwargs["stage"] != "terminal":
        return request
    constraints = (kwargs.get("verified_context") or {}).get("constraints") or {}
    policy = (kwargs.get("prior_drafts") or {}).get("policy") or {}
    series = policy.get("series", {})
    if not (policy.get("years") and constraints.get("issued_financing") and "interest_outside_cfo" in series):
        return request

    payload = json.loads(request.user)
    projection = payload["forecast_closing_debt_after_annual_years"]
    projection["annual_path"] = [
        row | annual_financing_row_v1(
            year=row["year"], closing_debt_cny=row["closing_debt_cny"],
            debt_repayment_cny=repayment, interest_outside_cfo_cny=interest,
            disclosed_unsettled_maturities_cny=financing_maturity_floor(constraints, row["year"]),
        )
        for row, repayment, interest in zip(
            projection["annual_path"], series["debt_repayment"]["values"],
            series["interest_outside_cfo"]["values"], strict=True,
        )
    ]
    return replace(request, user=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
