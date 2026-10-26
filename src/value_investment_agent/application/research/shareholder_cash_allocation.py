"""Apply explicit capital-call hypotheses to replayed public obligations."""
from copy import deepcopy
from decimal import Decimal as D, localcontext

from ...domain.valuation.finite_advantage_cash_path_v1 import _keys, _number, _reason

SCHEMA = 'source-bound-cash-allocation-policy-v2'


def allocate_inputs(*, policy, evidence_amounts, opening, capital, distribution, first_profit):
    _keys(policy, 'schema_version rationale timing_identity fund_call_weights digital_call_weights '
          'net_maintenance_gap_fraction requested_payout_ratios')
    if policy['schema_version'] != SCHEMA or policy['timing_identity'] != 'UNAPPROVED_CALL_SCHEDULE_NOT_DISCLOSED_DATES':
        raise ValueError('Explicit versioned conditional call schedule required')
    _reason(policy['rationale'])
    weights = {}
    for key in ('fund_call_weights', 'digital_call_weights', 'requested_payout_ratios'):
        raw = policy[key]
        if not isinstance(raw, list) or len(raw) != 10:
            raise ValueError('Ten annual allocation inputs required')
        values = [_number(x) for x in raw]
        if any(not 0 <= x <= 1 for x in values):
            raise ValueError('Invalid annual allocation fraction')
        if key != 'requested_payout_ratios' and sum(values) != 1:
            raise ValueError('Explicit commitment must be fully scheduled, not hidden in terminal')
        weights[key] = values
    gap_fraction = _number(policy['net_maintenance_gap_fraction'])
    if not 0 <= gap_fraction <= 1:
        raise ValueError('Invalid net maintenance sensitivity fraction')
    fund, digital = (_number(evidence_amounts[k]) for k in ('fund_uncalled_total_cny', 'digital_remaining_cny'))
    if min(fund, digital) < 0 or fund != D(opening['uncalled_fund_commitment_cny']):
        raise ValueError('Replayed commitments differ from inherited cash basis')
    start, cash, payouts = deepcopy(opening), deepcopy(capital), deepcopy(distribution)
    with localcontext() as context:
        context.prec = 48
        start['selected_project_budget_cny'] = str(D(start['selected_project_budget_cny']) + digital)
        for i, (row, payout) in enumerate(zip(cash, payouts, strict=True)):
            row['fund_call_cny'] = str(fund * weights['fund_call_weights'][i])
            row['project_cash_cny'] = str(D(row['project_cash_cny']) + digital * weights['digital_call_weights'][i])
            row['net_maintenance_gap_cny'] = str(_number(first_profit) * gap_fraction)
            payout['payout_ratio'] = str(weights['requested_payout_ratios'][i])
    return start, cash, payouts, dict(
        fund_uncalled_total_cny=str(fund), digital_remaining_cny=str(digital),
        schedule_identity=policy['timing_identity'],
        digital_treatment='ADDITIONAL_SELECTED_CAPITAL_ALLOCATION_NOT_FUND_OR_RECURRING_EXPENSE',
        reserve_treatment='CAPACITY_APPROPRIATION_NOT_CASH_EXPENSE',
        cash_floor_treatment='INHERITED_OPERATING_RESERVE_EXCLUDES_CAPITAL_CALL_RESERVE',
        net_maintenance_identity='EXPLICIT_NET_GAP_ASSUMPTION_NOT_OBSERVED_MAINTENANCE',
        rationale=policy['rationale'])
