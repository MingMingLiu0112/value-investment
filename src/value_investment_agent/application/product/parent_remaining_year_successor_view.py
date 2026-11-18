"""Public projection of a cold-replayed remaining-year owner-cash successor."""

from ..research.parent_remaining_year_successor import replay_parent_remaining_year_successor
from ..research.direct_owner_cash_research_v1 import _read


def read_parent_remaining_year_successor_view(*, root, receipt_binding, symbol, now):
    result = replay_parent_remaining_year_successor(
        root=root, receipt_binding=receipt_binding, now=now)
    receipt = _read(root, receipt_binding)
    spec = _read(root, receipt["spec_binding"])
    if (result["symbol"] != symbol or receipt["symbol"] != symbol
            or result["research_case"]["symbol"] != symbol
            or result["action"] != "no_order"
            or result["formal_eligibility"] is not False
            or result["successor_adopted"] is not False
            or result["main_range_adopted"] is not False
            or receipt["predecessor_binding"] != result["predecessor_binding"]
            or result["input_descriptor_sha256"] != receipt["input_descriptor_sha256"]):
        raise ValueError("SUCCESSOR_PUBLIC_IDENTITY_OR_ADOPTION_INVALID")
    compiled = result["compiled"]
    annual = {name: row["calculation"]["annual_rows"]
              for name, row in compiled["scenarios"].items()}
    if set(annual) != {"bear", "base", "bull"}:
        raise ValueError("SUCCESSOR_PUBLIC_SCENARIOS_INCOMPLETE")
    return dict(
        schema_version="first-research-input-view-v1",
        receipt_schema_version="parent-remaining-year-successor-receipt-v1",
        status="SOURCE_BOUND_FIRST_INPUT_COMPILED", reason=None,
        symbol=symbol, action="no_order", formal_eligibility=False,
        main_range_adopted=False, main_valuation_range=None,
        current_price=None, condition_price=None, personal_quantity=None,
        user_acceptance="NOT_CONFIRMED",
        scope="SOURCE_REPLAYED_REMAINING_YEAR_OWNER_CASH_SUCCESSOR_NOT_ADOPTED",
        receipt_binding=receipt_binding,
        predecessor_binding=result["predecessor_binding"],
        input_descriptor_sha256=result["input_descriptor_sha256"],
        financial_basis=spec["period_end"], research_as_of=spec["research_as_of"],
        input_computed_at=spec["computed_at"],
        research_case=result["research_case"], valuation=result["valuation"],
        valuation_status="conditional_research_only",
        annual_ledgers={name: dict(rows=rows) for name, rows in annual.items()},
        annual_recalculations=result["annual_recalculations"],
        blockers=result["research_result"]["blockers"],
        source_bindings=result["source_bindings"],
        compilation_scope="SOURCE_REPLAYED_REMAINING_YEAR_OWNER_CASH_SUCCESSOR",
        scenario_label_scope="CONDITIONAL_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
        sources=result["package"]["sources"],
        operating_assumptions=spec["scenarios"],
        source_review="QUARTER_SOURCE_AND_PREDECESSOR_COLD_REPLAYED_NOT_APPROVAL",
        investment_conclusion="UNAPPROVED_CONDITIONAL_OWNER_CASH_RESEARCH",
        direct_owner_cash=dict(
            method="DIRECT_CFO_LESS_EXPLICIT_CAPITAL_DEBT_AND_CONSTRAINED_DISTRIBUTIONS",
            valuation_basis=spec["period_end"], scope="ISSUER_PARENT_STANDALONE",
            annual_rows=annual, assumptions=compiled["assumptions"],
            conditional_price=None, source_refs=result["source_bindings"],
            remaining_year_review=dict(
                schema_version="parent-remaining-year-successor-receipt-v1",
                status="SOURCE_BOUND_CONDITIONAL_SUCCESSOR", action="no_order",
                formal_eligibility=False, successor_adopted=False,
                candidate_binding=receipt_binding,
                predecessor_binding=result["predecessor_binding"],
                input_descriptor_sha256=result["input_descriptor_sha256"],
                annual_recalculations=result["annual_recalculations"],
                scenarios=compiled["scenarios"],
                current_price_qualified=False)))
