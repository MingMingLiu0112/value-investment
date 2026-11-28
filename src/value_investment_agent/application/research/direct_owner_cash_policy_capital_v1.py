"""Versioned capital context and debt consistency for new V3 policy tasks.

Historical tasks keep their original request bytes. This is forecast arithmetic,
not verification of borrowing availability or the opening debt assumption.
"""
from dataclasses import replace
from decimal import Decimal, localcontext
import json

VERSION = "POLICY_OPENING_CAPITAL_V1"


def opening_debt_basis(opening, facts):
    term = opening["debt"]
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        if "linear_terms" in term:
            value = sum(Decimal(facts[row["anchor"]]["value_cny"]) *
                        Decimal(row["factor"]) for row in term["linear_terms"])
        elif "anchor" in term:
            value = Decimal(facts[term["anchor"]]["value_cny"]) * Decimal(term.get("factor", "1"))
        else:
            value = Decimal(term["value"])
    if not value.is_finite() or value < 0:
        raise ValueError("PARENT_V3_OPENING_DEBT_INVALID")
    anchor = term.get("anchor")
    field = facts[anchor]["field"] if anchor is not None else None
    return dict(amount_cny=str(value), classification=term["classification"],
                fact_field=field,
                scope=("ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"
                       if term["classification"] == "FORECAST_ASSUMPTION" and field == "liabilities_cny"
                       else "SPECIFIED_OPENING_DEBT_BASIS"),
                evidence_anchors=([anchor] if anchor is not None else
                    [row["anchor"] for row in term.get("linear_terms", [])]
                    or term.get("evidence_anchors", [])),
                rationale=term.get("rationale"), counter_evidence=term.get("counter_evidence"),
                reopen_condition=term.get("reopen_condition"))


def policy_capital_request(request, basis):
    payload = json.loads(request.user)
    payload["opening_debt_basis"] = basis
    payload["debt_balance_contract"] = dict(
        version=VERSION, classification="FORECAST_ARITHMETIC_NOT_FINANCING_FACT",
        equation="closing_debt = opening_debt + new_borrowing - debt_repayment",
        negative_balance_allowed=False, refinancing_guaranteed=False)
    return replace(request, user=json.dumps(payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")),
        transport_output_contract=(request.transport_output_contract or str()) +
        " Apply opening_debt_basis before submitting annual borrowing and repayment. "
        "Carry each closing principal balance into the next year; none may be negative. "
        "Do not change the supplied opening amount or manufacture borrowing to pass. "
        "A forecast or all-liabilities upper bound is not verified financing principal. "
        "Keep observed receipts, conditional issue proceeds and contractual maturities "
        "distinct; explain forecast funding and its uncertainty. Debt arithmetic "
        "does not establish actual liquidity, refinancing permission or distributability.")


def validate_policy_debt(basis, policy):
    years = policy["years"]
    borrowings = policy["series"]["new_borrowing"]["values"]
    repayments = policy["series"]["debt_repayment"]["values"]
    if not years or len(years) != len(borrowings) or len(years) != len(repayments):
        raise ValueError("PARENT_V3_FORECAST_DEBT_YEARS_INVALID")
    if any(type(year) is not int for year in years) or years != list(range(years[0], years[0]+len(years))):
        raise ValueError("PARENT_V3_FORECAST_DEBT_YEARS_INVALID")
    path = []
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        balance = Decimal(basis["amount_cny"])
        if not balance.is_finite() or balance < 0:
            raise ValueError("PARENT_V3_OPENING_DEBT_INVALID")
        for year, borrowing, repayment in zip(years, borrowings, repayments, strict=True):
            borrowed, repaid = Decimal(borrowing), Decimal(repayment)
            if any(not value.is_finite() or value < 0 for value in (borrowed, repaid)):
                raise ValueError("PARENT_V3_NEGATIVE_POLICY_AMOUNT")
            opening = balance
            balance += borrowed - repaid
            if balance < 0:
                raise ValueError("PARENT_V3_FORECAST_DEBT_NEGATIVE")
            path.append(dict(year=year, opening_debt_cny=str(opening),
                             new_borrowing_cny=str(borrowed), debt_repayment_cny=str(repaid),
                             closing_debt_cny=str(balance)))
    return path
