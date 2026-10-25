"""Ten-year product/funds research successor; no model or approval registry.

Keep the five supplied product hypotheses; append five explicit product paths.
Use the existing owner-equivalent cash contract, not total-equity ROE fade.
Source/PIT authentication belongs to the caller; arithmetic is not admission.
"""
from copy import deepcopy
from decimal import Decimal as D, localcontext

from .finite_advantage_cash_path_v1 import (
    SCOPE, _capital, _distribution, _keys, _number, _plain, _rate, _reason,
)
from .operating_product_paths import POLICY_FIELDS


VERSION = 'product-continuation-cash-path-v1'
PRODUCTS = 'moutai series other'
EXPENSES = 'taxes_surcharges selling administration research'
PRODUCT_ROW_FIELDS = (
    'year opening_product_reference_revenue_cny product_revenue_cny drivers revenue cost '
    'expenses other_pre_tax_balance legacy_pre_tax_profit effective_tax_rate parent_share '
    'net_parent_nonrecurring_difference legacy_ex_parent')
TOLERANCE = D('1e-24')


def _equal(left, right):
    if abs(left - right) > TOLERANCE:
        raise ValueError('Product accounting/continuity replay mismatch')


def _drivers(value):
    _keys(value, ' '.join(sorted(POLICY_FIELDS)))
    result = {key: _number(item) for key, item in value.items()}
    if (not 0 <= result['cost_ratio'] <= 1
            or any(result[key] <= -1 for key in POLICY_FIELDS if key != 'cost_ratio')):
        raise ValueError('Unsupported product growth or cost ratio')
    return result


def _amounts(previous, drivers):
    amounts = {key: previous[key] * (1 + drivers[key + '_volume_growth']) *
               (1 + drivers[key + '_realization_growth']) for key in ('moutai', 'series')}
    amounts['other'] = previous['other'] * (1 + drivers['other_revenue_growth'])
    return amounts


def _operating_rows(first_five, continuation):
    if (not isinstance(first_five, list) or len(first_five) != 5
            or not isinstance(continuation, list) or len(continuation) != 5):
        raise ValueError('Exactly five original and five continuation product years required')
    rows, previous, anchor = [], None, None
    for year, raw in enumerate(first_five, 1):
        _keys(raw, PRODUCT_ROW_FIELDS)
        if type(raw['year']) is not int or raw['year'] != year:
            raise ValueError('Original product year mismatch')
        _keys(raw['opening_product_reference_revenue_cny'], PRODUCTS)
        _keys(raw['product_revenue_cny'], PRODUCTS)
        _keys(raw['expenses'], EXPENSES)
        row = {key: _number(raw[key]) for key in (
            'revenue', 'cost', 'other_pre_tax_balance', 'legacy_pre_tax_profit',
            'net_parent_nonrecurring_difference', 'legacy_ex_parent')}
        row.update(year=year, drivers=_drivers(raw['drivers']),
            effective_tax_rate=_rate(raw['effective_tax_rate']), parent_share=_rate(raw['parent_share']),
            opening_product_reference_revenue_cny={key: _number(value) for key, value in raw['opening_product_reference_revenue_cny'].items()},
            product_revenue_cny={key: _number(value) for key, value in raw['product_revenue_cny'].items()},
            expenses={key: _number(value) for key, value in raw['expenses'].items()})
        if (row['revenue'] <= 0 or row['legacy_pre_tax_profit'] <= 0 or row['legacy_ex_parent'] <= 0
                or row['parent_share'] <= 0 or row['effective_tax_rate'] >= 1
                or min(row['cost'], *row['expenses'].values(),
                       *row['opening_product_reference_revenue_cny'].values(),
                       *row['product_revenue_cny'].values()) < 0):
            raise ValueError('Unsupported product statement signs')
        calculated = _amounts(row['opening_product_reference_revenue_cny'], row['drivers'])
        for key in calculated:
            _equal(calculated[key], row['product_revenue_cny'][key])
            if previous is not None:
                _equal(row['opening_product_reference_revenue_cny'][key], previous['product_revenue_cny'][key])
        _equal(sum(calculated.values()), row['revenue'])
        _equal(row['cost'], row['revenue'] * row['drivers']['cost_ratio'])
        _equal(row['legacy_pre_tax_profit'], row['revenue'] - row['cost'] -
               sum(row['expenses'].values()) + row['other_pre_tax_balance'])
        _equal(row['legacy_ex_parent'], row['legacy_pre_tax_profit'] *
               (1-row['effective_tax_rate']) * row['parent_share'] - row['net_parent_nonrecurring_difference'])
        if anchor is not None:
            for key in ('other_pre_tax_balance', 'effective_tax_rate', 'parent_share', 'net_parent_nonrecurring_difference'):
                _equal(row[key], anchor[key])
            for key in row['expenses']:
                _equal(row['expenses'][key], anchor['expenses'][key] * row['revenue'] / anchor['revenue'])
        else:
            anchor = row
        rows.append(row)
        previous = row
    anchor = rows[-1]
    for year, raw in enumerate(continuation, 6):
        drivers = _drivers(raw)
        amounts = _amounts(previous['product_revenue_cny'], drivers)
        revenue = sum(amounts.values())
        cost = revenue * drivers['cost_ratio']
        expenses = {key: value * (revenue / anchor['revenue']) for key, value in anchor['expenses'].items()}
        pbt = revenue - cost - sum(expenses.values()) + anchor['other_pre_tax_balance']
        # Anchored delta preserves the supplied L5 exactly in the flat branch.
        profit = anchor['legacy_ex_parent'] + (pbt - anchor['legacy_pre_tax_profit']) * (
            1-anchor['effective_tax_rate']) * anchor['parent_share']
        row = dict(year=year, opening_product_reference_revenue_cny=dict(previous['product_revenue_cny']),
            product_revenue_cny=amounts, drivers=drivers, revenue=revenue, cost=cost,
            expenses=expenses, other_pre_tax_balance=anchor['other_pre_tax_balance'],
            legacy_pre_tax_profit=pbt, effective_tax_rate=anchor['effective_tax_rate'],
            parent_share=anchor['parent_share'], net_parent_nonrecurring_difference=anchor['net_parent_nonrecurring_difference'],
            legacy_ex_parent=profit)
        rows.append(row)
        previous = row
    return rows


def build_product_continuation_cash_path(*, opening_state, first_five_product_rows,
                                       continuation_policy, capital_cash_rows,
                                       distribution_rows, cost_of_equity,
                                       incremental_cash_yield, terminal_policy=None):
    """Pure LOW research, exactly ten annual steps; no calendar/PIT invention.

    opening_state/capital_cash_rows/distribution_rows use the finite cash v1
    exact contracts. continuation_policy is five original six-driver dicts.
    Terminal exact keys: method/rationale/operating_continuation/
    distribution_constraint_rationale/capital_cash_row/distribution_row.
    method=STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT;
    operating_continuation=FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT.
    No growth, price, cash return, legal capacity or terminal support is defaulted.
    """
    _keys(opening_state, 'scope currency book_equity_cny cash_cny unremitted_assets_cny '
          'distribution_capacity_cny cash_floor_cny uncalled_fund_commitment_cny '
          'selected_project_budget_cny ordinary_shares')
    if opening_state['scope'] != SCOPE or opening_state['currency'] != 'CNY':
        raise ValueError('Explicit owner-equivalent CNY scope required')
    if any(not isinstance(rows, list) or len(rows) != 10 for rows in (capital_cash_rows, distribution_rows)):
        raise ValueError('Exactly ten explicit cash/distribution years required')
    with localcontext() as context:
        context.prec = 48
        operating = _operating_rows(first_five_product_rows, continuation_policy)
        capital = [_capital(row, year, SCOPE) for year, row in enumerate(capital_cash_rows, 1)]
        distribution = [_distribution(row, year) for year, row in enumerate(distribution_rows, 1)]
        ke, q = map(_number, (cost_of_equity, incremental_cash_yield))
        if not 0 < ke < 1 or q < 0:
            raise ValueError('Invalid Ke or explicit incremental cash yield')
        b, c, u, capacity, floor, fund_remaining, project_remaining, shares = map(_number, (
            opening_state[key] for key in ('book_equity_cny', 'cash_cny', 'unremitted_assets_cny',
                'distribution_capacity_cny', 'cash_floor_cny', 'uncalled_fund_commitment_cny',
                'selected_project_budget_cny', 'ordinary_shares')))
        if (b <= 0 or min(c, u, capacity, floor, fund_remaining, project_remaining) < 0
                or shares <= 0 or shares != shares.to_integral_value() or c < floor or b < c+u):
            raise ValueError('Invalid opening cash/equity state')
        b0, c0, a = b, c, b-c-u
        rows, blockers = [], []
        pv_ri = pv_d = D(0)
        for driver, cash, allocation in zip(operating, capital, distribution):
            year = driver['year']
            n, fund, project, cash_input = cash
            payout, held_fraction, release_fraction, reserve = allocation
            legacy = driver['legacy_ex_parent']
            income = q*(c-c0)
            p = legacy+income
            if legacy <= 0 or p <= 0:
                blockers.append('YEAR_%s_NONPOSITIVE_PRODUCT_OR_TOTAL_PROFIT' % year)
                break
            held, released = p*held_fraction, u*release_fraction
            m, d = p-held+released, payout*p
            next_b, next_c, next_u = b+p-d, c+m-n-fund-d, u+held-released
            next_a, next_capacity = a+n+fund, capacity+m-reserve*p-d
            ri, discount = p-ke*b, (1+ke)**year
            checks = dict(cash_floor=next_c >= floor, distribution_capacity=next_capacity >= 0,
                fund_budget=fund <= fund_remaining, project_budget=project <= project_remaining,
                residual_net_equity=next_a >= 0)
            residual = next_b-next_c-next_u-next_a
            _equal(residual, D(0))
            rows.append(dict(year=year, legacy_profit_cny=legacy, incremental_cash_income_cny=income,
                profit_cny=p, opening_book_cny=b, opening_cash_cny=c, distribution_cny=d,
                upstream_funds_cny=m, withheld_cny=held, released_cny=released,
                net_capital_cash_need_cny=n, fund_call_cny=fund, closing_book_cny=next_b,
                closing_cash_cny=next_c, closing_unremitted_assets_cny=next_u,
                residual_net_equity_component_cny=next_a, distribution_capacity_proxy_cny=next_capacity,
                ri_cny=ri, pv_ri_cny=ri/discount, pv_distribution_cny=d/discount,
                clean_surplus_residual_cny=residual, capital_cash_input=cash_input,
                distribution_input=deepcopy(distribution_rows[year-1]), checks=checks))
            if not all(checks.values()):
                blockers.extend('YEAR_%s_%s' % (year, key.upper()) for key, ok in checks.items() if not ok)
                break
            pv_ri += ri/discount
            pv_d += d/discount
            b, c, u, a, capacity = next_b, next_c, next_u, next_a, next_capacity
            fund_remaining -= fund
            project_remaining -= project
        terminal = dict(status='UNSUPPORTED', terminal_ri_cny=None, reasons=[])
        valuation = dict(usable=False, equity_value_cny=None, per_share_cny=None,
            pv_explicit_ri_cny=pv_ri, pv_terminal_ri_cny=None, ddm_equity_value_cny=None,
            ri_ddm_residual_cny=None, terminal_value_pv_share=None)
        if not blockers and len(rows) == 10:
            if terminal_policy is None:
                terminal['reasons'].append('EXPLICIT_TERMINAL_POLICY_MISSING')
            else:
                _keys(terminal_policy, 'method rationale operating_continuation '
                      'distribution_constraint_rationale capital_cash_row distribution_row')
                _reason(terminal_policy['rationale'])
                _reason(terminal_policy['distribution_constraint_rationale'])
                n, fund, project, tc = _capital(terminal_policy['capital_cash_row'], 11, SCOPE)
                gap = (_number(tc['net_maintenance_gap_cny']) if tc['maintenance_basis'] == 'EXPLICIT_NET_GAP_ASSUMPTION'
                       else _number(tc['maintenance_capex_cny'])-_number(tc['matched_da_cny']))
                payout, held_fraction, release_fraction, reserve = _distribution(terminal_policy['distribution_row'], 11)
                lp = operating[-1]['legacy_ex_parent']
                income = q*(c-c0)
                p = lp+income
                checks = dict(explicit_method=terminal_policy['method'] == 'STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT',
                    explicit_product_continuation=terminal_policy['operating_continuation'] == 'FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT',
                    positive_product_and_total_profit=lp > 0 and p > 0,
                    no_unremitted_assets=u == 0, no_unpaid_selected_commitments=fund_remaining == 0 and project_remaining == 0,
                    no_new_funding=fund == 0 and project == 0, net_maintenance_gap_zero=gap == 0,
                    no_recurring_wc_release_or_investment=_number(tc['operating_wc_increase_cny']) == 0,
                    net_maintenance_wc_balanced=n == 0,
                    full_funds_conversion=held_fraction == 0 and release_fraction == 0,
                    supported_full_distribution=payout == 1 and reserve == 0,
                    cash_floor=c >= floor, capacity_non_depleting=capacity >= 0)
                terminal.update(checks=checks, policy=deepcopy(terminal_policy), legacy_profit_cny=lp,
                    incremental_cash_income_cny=income, next_profit_cny=p, next_distribution_cny=payout*p,
                    next_cash_cny=c+p*(1-held_fraction-payout)-n-fund, next_book_cny=b+p*(1-payout))
                terminal['reasons'] = [key for key, ok in checks.items() if not ok]
                if all(checks.values()):
                    tv = p/ke
                    tri = tv-b
                    value = b0+pv_ri+tri/(1+ke)**10
                    ddm = pv_d+tv/(1+ke)**10
                    _equal(value, ddm)
                    terminal.update(status='CONDITIONAL_TERMINAL_SUPPORTED', terminal_ri_cny=tri,
                        terminal_equity_cash_value_cny=tv, first_year_ri_cny=p-ke*b)
                    valuation.update(usable=True, equity_value_cny=value, per_share_cny=value/shares,
                        pv_terminal_ri_cny=tri/(1+ke)**10, ddm_equity_value_cny=ddm,
                        ri_ddm_residual_cny=value-ddm, terminal_value_pv_share=(tv/(1+ke)**10)/ddm)
            blockers.extend('TERMINAL_'+reason for reason in terminal['reasons'])
        return _plain(dict(version=VERSION, status='CONDITIONAL_PRODUCT_CONTINUATION_RESEARCH' if valuation['usable'] else 'VALUATION_UNSUPPORTED',
            scope=SCOPE, confidence='LOW', action='no_order', formal_eligibility=False, economic_approval=False,
            price_admission=False, primary_valuation_changed=False, normalized_parent_profit_cny=None,
            operating_rows=operating, cash_rows=rows, terminal=terminal, valuation=valuation, blockers=blockers,
            opening_state=deepcopy(opening_state), continuation_policy=deepcopy(continuation_policy),
            cost_of_equity=ke, incremental_cash_yield=q,
            limitations=[
                'Product L includes an assumed historical finance/other balance; it is not pure operating profit or normalized earnings.',
                'q applies only to changes from opening research cash, not all book capital or fund assets.',
                'M=P-withheld+release is a LOW owner-equivalent funds hypothesis, not parent CFO/legal profit.',
                'Residual A=B-C-U is a net-equity component, not verified assets or NAV.',
                'Capital needs are deducted once here; WC excludes cash/customer funds; other noncash/net financing are explicit zero hypotheses.',
                'Project/fund schedules and reserve/capacity mappings are research hypotheses, not verified payables or legal approval.',
                'Flat terminal product levels, finance balance, tax and attribution require sustained economics; no competitive-advantage duration is proven.',
                'Terminal DDM value includes retained cash earnings; do not add cash again. Research steps do not establish calendar periods or historical PIT.']))
