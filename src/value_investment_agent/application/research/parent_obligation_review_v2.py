"""Source-bound historical obligation stresses, separate from current valuation."""
from decimal import Decimal
import hashlib
import json

from value_investment_agent.domain.research.parent_obligation_pressure_v2 import (
    evaluate_parent_obligation_pressure,
)
from value_investment_agent.infrastructure.filings.parent_obligation_sources_v2 import (
    load_parent_obligation_snapshot, load_frozen_cash_floor_assumption,
    load_official_parent_constraint_disclosures,
)


def review_parent_obligations_v2(*, root, native_path, floor_assumption_path,
                               cutoff, hypothetical_additional_distribution_cny,
                               future_investment_reserve_cny, constraint_bundle_root=None):
    """Four alternative stresses expose uncertainty; none is a selected forecast.

    Caller supplies hypothetical *additional* distribution, not annual-policy
    attribution. Zero future investment is permissible only as an explicit
    stress input, never a disclosure that necessary investment is zero.
    """
    snapshot = load_parent_obligation_snapshot(root=root, native_path=native_path, cutoff=cutoff)
    floor = load_frozen_cash_floor_assumption(root=root, relative_path=floor_assumption_path, cutoff=cutoff)
    scenarios = []
    for other, overlap in ((False, False), (False, True), (True, False), (True, True)):
        scenario = dict(
            scenario_id=('ALL_CURRENT_BOOK_RESERVE' if other else 'IDENTIFIED_CURRENT_DEBT_ONLY')
                        + ('_FLOOR_INCLUDES_DEBT' if overlap else '_FLOOR_ADDITIONAL'),
            reserve_other_current=other, reserve_noncurrent_borrowings=False,
            cash_floor_cny=floor['value'], floor_includes_debt=overlap,
            future_investment_reserve_cny=future_investment_reserve_cny,
            hypothetical_additional_distribution_cny=hypothetical_additional_distribution_cny,
        )
        scenarios.append(evaluate_parent_obligation_pressure(snapshot=snapshot, scenario=scenario))
    values = [Decimal(row['conditional_cash_residual_cny']) for row in scenarios]
    result = dict(schema_version='parent-obligation-review-v2',
        status='SOURCE_BOUND_HISTORICAL_CONDITIONAL_STRESSES',
        symbol=snapshot['symbol'], financial_basis=snapshot['as_of'],
        cutoff=cutoff.isoformat(), snapshot=snapshot, floor_assumption=floor,
        scenarios=scenarios,
        illustrative_residual_span_cny=dict(minimum=str(min(values)), maximum=str(max(values)),
            classification='SPAN_OF_LISTED_ASSUMPTIONS_NOT_PROBABILITY_OR_CAPACITY_RANGE'),
        key_findings=[
            'Standalone short-term borrowings and current noncurrent liabilities are different rows; both are reserved.',
            'Other payables include declared dividend; subtract it once before constructing the residual.',
            'Consolidated principal/interest/lease components are not assigned to the parent.',
            'The old rationale says maintain a cash floor, but provides no evidenced operating/debt allocation. Additive reservation preserves minimum-cash semantics; debt-inclusive variants redefine it as a combined buffer and do not validate the original model.',
            'All-current reservation treats book liabilities as a stress buffer; contract liabilities need not settle in cash.',
            'The noncurrent borrowing balance is disclosed but not moved into the current horizon without a maturity basis.',
            'Historical CapEx, debt payments and the already reserved dividend are not new incremental cash uses.',
        ],
        unresolved=[
            'Parent-specific principal/interest/lease decomposition and exact maturity dates',
            'Post-snapshot parent repayment, borrowing and cash rollforward',
            'Cash nature, counterparties and settlement dates of remaining other payables',
            'Verified minimum operating reserve and necessary future investment',
            'Legal distribution adjustments and current parent distributable profit',
        ],
        hypothetical_distribution_is_declared_liability=False,
        annual_policy_fulfillment_assessed=False, capacity_proven=False,
        formal_eligibility=False, research_admitted=False, financial_admission=False,
        economic_approval=False, price_admitted=False, strategy_admitted=False,
        action_admitted=False, current_parent_cash_cny=None,
        current_distribution_capacity_cny=None, actual_funding_shortfall_cny=None,
        action='no_order')
    result['official_constraint_disclosures'] = (
        load_official_parent_constraint_disclosures(bundle_root=constraint_bundle_root, cutoff=cutoff)
        if constraint_bundle_root is not None else
        dict(status='NOT_LOADED', legal_distribution_certified=False, action='no_order')
    )
    result['review_fingerprint'] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    return result
