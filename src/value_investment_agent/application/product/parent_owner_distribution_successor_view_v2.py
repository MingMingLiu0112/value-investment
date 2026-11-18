"""Public projection of a cold-replayed implemented owner distribution.

The view exposes the source-bound v2 calculation without adopting a main
valuation range, qualifying a price, or granting any formal action.
"""

from ..research.direct_owner_cash_research_v1 import _read
from ..research.parent_owner_distribution_successor_v2 import (
    replay_parent_owner_distribution_successor,
)


def read_parent_owner_distribution_successor_view(*, root, receipt_binding, symbol, now):
    result = replay_parent_owner_distribution_successor(
        root=root, receipt_binding=receipt_binding, now=now,
    )
    receipt = _read(root, receipt_binding)
    spec = _read(root, receipt["spec_binding"])
    if (
        result["symbol"] != symbol
        or receipt["symbol"] != symbol
        or result["research_case"]["symbol"] != symbol
        or result["action"] != "no_order"
        or result["formal_eligibility"] is not False
        or result["successor_adopted"] is not False
        or result["main_range_adopted"] is not False
        or receipt["predecessor_binding"] != result["predecessor_binding"]
        or result["input_descriptor_sha256"] != receipt["input_descriptor_sha256"]
    ):
        raise ValueError("OWNER_DISTRIBUTION_PUBLIC_IDENTITY_OR_ADOPTION_INVALID")

    calculations = result["valuation"]["assumptions"]["scenario_calculations"]
    if set(calculations) != {"bear", "base", "bull"}:
        raise ValueError("OWNER_DISTRIBUTION_PUBLIC_SCENARIOS_INCOMPLETE")
    distributions = {}
    annual = {}
    for name, calculation in calculations.items():
        rows = calculation["annual_rows"]
        annual[name] = rows
        distributions[name] = [
            {
                "year": row["year"],
                "scheduled_owner_distribution_cny": row[
                    "scheduled_owner_distribution_cny"
                ],
                "conditional_owner_distribution_cny": row[
                    "conditional_distribution_cny"
                ],
                "total_owner_distribution_cny": row[
                    "total_owner_distribution_cny"
                ],
            }
            for row in rows
        ]

    return dict(
        schema_version="first-research-input-view-v1",
        receipt_schema_version="parent-owner-distribution-successor-receipt-v2",
        status="SOURCE_BOUND_FIRST_INPUT_COMPILED",
        reason=None,
        symbol=symbol,
        action="no_order",
        formal_eligibility=False,
        successor_adopted=False,
        main_range_adopted=False,
        main_valuation_range=None,
        current_price=None,
        condition_price=None,
        personal_quantity=None,
        user_acceptance="NOT_CONFIRMED",
        scope="SOURCE_REPLAYED_IMPLEMENTED_OWNER_DISTRIBUTION_NOT_ADOPTED",
        receipt_binding=receipt_binding,
        predecessor_binding=result["predecessor_binding"],
        input_descriptor_sha256=result["input_descriptor_sha256"],
        financial_basis=result["valuation"]["valuation_date"],
        research_as_of=spec["research_as_of"],
        input_computed_at=spec["computed_at"],
        research_case=result["research_case"],
        valuation=result["valuation"],
        valuation_status="conditional_research_only",
        scenario_valuations={
            name: result["valuation"][name + "_value"]
            for name in ("bear", "base", "bull")
        },
        annual_ledgers={name: {"rows": rows} for name, rows in annual.items()},
        owner_distributions=distributions,
        implemented_distribution=result["distribution"],
        distribution_evidence=result["distribution_evidence"],
        blockers=result["research_result"]["blockers"],
        source_bindings=result["source_bindings"],
        compilation_scope="SOURCE_REPLAYED_IMPLEMENTED_OWNER_DISTRIBUTION_SUCCESSOR",
        scenario_label_scope="CONDITIONAL_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
        sources=result["package"]["sources"],
        operating_assumptions=result["compiled"]["scenarios"],
        source_review="PREDECESSOR_AND_IMPLEMENTED_DISTRIBUTION_COLD_REPLAYED_NOT_APPROVAL",
        investment_conclusion="UNAPPROVED_CONDITIONAL_OWNER_CASH_RESEARCH",
        direct_owner_cash=dict(
            method="DIRECT_CFO_LESS_EXPLICIT_CAPITAL_DEBT_AND_CONSTRAINED_DISTRIBUTIONS_V2",
            valuation_basis=result["valuation"]["valuation_date"],
            scope="ISSUER_PARENT_STANDALONE",
            annual_rows=annual,
            owner_distributions=distributions,
            implemented_distribution=result["distribution"],
            conditional_price=None,
            source_refs=result["source_bindings"],
        ),
    )
