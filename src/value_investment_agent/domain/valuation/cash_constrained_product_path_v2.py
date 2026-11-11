"""Bound distributions using the existing ten-year product/cash calculator.

This is a versioned allocation adapter, not a second valuation engine. The
original kernel owns earnings, capital, clean surplus, terminal and RI/DDM.
Capacity remains an explicitly conditional owner-equivalent proxy, not law.
"""
from copy import deepcopy
from decimal import Decimal as D, ROUND_DOWN, localcontext

from .finite_advantage_cash_path_v1 import _keys, _reason, _number, _plain
from .product_continuation_cash_path_v1 import build_product_continuation_cash_path

VERSION = 'cash-constrained-product-path-v2'


def build_cash_constrained_product_path(*, allocation_policy, **arguments):
    _keys(allocation_policy, 'schema_version rationale capacity_scope')
    if (allocation_policy['schema_version'] != VERSION or
            allocation_policy['capacity_scope'] != 'CONDITIONAL_OWNER_EQUIVALENT_NOT_LEGAL_PARENT_CAPACITY'):
        raise ValueError('Explicit conditional cash-allocation contract required')
    _reason(allocation_policy['rationale'])
    working = deepcopy(arguments)
    requested = deepcopy(working['distribution_rows'])
    if not isinstance(requested, list) or len(requested) != 10:
        raise ValueError('Ten requested distribution years required')
    # Validate original inputs before deriving any allocation. A zero-distribution
    # probe only asks the existing kernel for pre-distribution available funds.
    for row in working['distribution_rows']:
        row['payout_ratio'] = '0'
    traces = []
    with localcontext() as context:
        context.prec = 48
        for index, desired in enumerate(requested):
            target = _number(desired['payout_ratio'])
            if not 0 <= target <= 1:
                raise ValueError('Requested distribution fraction outside [0,1]')
            probe = build_product_continuation_cash_path(**working)
            if len(probe['cash_rows']) <= index or not all(probe['cash_rows'][index]['checks'].values()):
                probe.update(allocation_version=VERSION, allocation_policy=deepcopy(allocation_policy),
                             allocation_trace=_plain(traces))
                return probe  # Even paying zero cannot repair this cash/commitment failure.
            row = probe['cash_rows'][index]
            profit = D(row['profit_cny'])
            cash = D(row['closing_cash_cny']) - D(arguments['opening_state']['cash_floor_cny'])
            capacity = D(row['distribution_capacity_proxy_cny'])
            wanted = target * profit
            budget = min(wanted, cash, capacity)
            # Never use rounding to spend more than either constraint allows.
            actual_ratio = target if budget == wanted else (budget / profit).quantize(D('1e-40'), rounding=ROUND_DOWN)
            working['distribution_rows'][index]['payout_ratio'] = str(actual_ratio)
            traces.append(dict(year=index+1, requested_distribution_cny=wanted,
                cash_available_before_distribution_cny=cash,
                capacity_before_distribution_cny=capacity,
                allowed_distribution_cny=actual_ratio*profit,
                distribution_limited_by=[name for name, amount in
                    (('CASH_FLOOR', cash), ('DISTRIBUTION_CAPACITY_PROXY', capacity))
                    if amount < wanted and amount == budget],
                requested_payout_ratio=target, actual_payout_ratio=actual_ratio))
        result = build_product_continuation_cash_path(**working)
        fund = D(arguments['opening_state']['uncalled_fund_commitment_cny'])
        project = D(arguments['opening_state']['selected_project_budget_cny'])
        for row, trace in zip(result['cash_rows'], traces):
            fund -= D(row['fund_call_cny'])
            project -= D(row['capital_cash_input']['project_cash_cny'])
            row.update(_plain(trace), closing_uncalled_fund_commitment_cny=str(fund),
                       closing_selected_project_budget_cny=str(project))
        result.update(allocation_version=VERSION, allocation_policy=deepcopy(allocation_policy),
                      allocation_trace=_plain(traces))
        result['limitations'].append(
            'Distribution is capped by modeled cash and capacity; this does not certify subsidiary remittance, '
            'parent legal earnings, dividend approval or an investment action. No missing input is filled.')
        return result
