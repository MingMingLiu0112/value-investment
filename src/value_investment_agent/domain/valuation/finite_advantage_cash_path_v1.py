"""Conditional owner-equivalent cash/clean-surplus research, never approval.

No source authentication or standalone-parent financial forecast is performed.
The caller binds sources and explicit LOW assumptions before/after calculation.
All amounts are CNY; annual steps are research periods, not historical facts.
"""
from decimal import Decimal, InvalidOperation, localcontext


SCOPE = 'ordinary_owner_equivalent_cash_mapping'
VERSION = 'finite-advantage-cash-path-v1'


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('Explicit finite decimal required; no float/bool/missing values')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid decimal') from error
    if not result.is_finite():
        raise ValueError('Finite decimal required')
    return result


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError('Exact fields required: ' + expected)


def _reason(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Explicit research rationale required')


def _rate(value):
    result = _number(value)
    if not 0 <= result <= 1:
        raise ValueError('Fraction outside [0,1]')
    return result


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _capital(row, year, scope):
    common = ('year scope rationale funding_treatment maintenance_basis '
              'project_cash_cny maintenance_project_overlap_cny '
              'operating_wc_increase_cny fund_call_cny '
              'other_noncash_adjustment_cny net_financing_cny')
    basis = row.get('maintenance_basis') if isinstance(row, dict) else None
    extra = (' net_maintenance_gap_cny' if basis == 'EXPLICIT_NET_GAP_ASSUMPTION'
             else ' maintenance_capex_cny matched_da_cny')
    _keys(row, common + extra)
    if type(row['year']) is not int or row['year'] != year or row['scope'] != scope:
        raise ValueError('Capital year/scope must match opening state exactly')
    _reason(row['rationale'])
    if row['funding_treatment'] != 'NET_NEEDS_DEDUCTED_HERE_NOT_IN_UPSTREAM_MAPPING':
        raise ValueError('Capital needs must be deducted exactly once, not also upstream')
    project, overlap, wc, fund, other, financing = map(_number, (
        row['project_cash_cny'], row['maintenance_project_overlap_cny'],
        row['operating_wc_increase_cny'], row['fund_call_cny'],
        row['other_noncash_adjustment_cny'], row['net_financing_cny']))
    if min(project, overlap, fund) < 0 or overlap > project:
        raise ValueError('Invalid project/fund/overlap amounts')
    if other != 0 or financing != 0:
        raise ValueError('This bounded contract requires explicit zero other noncash/net financing hypotheses')
    with localcontext() as context:
        context.prec = 48
        if basis == 'EXPLICIT_NET_GAP_ASSUMPTION':
            gap = _number(row['net_maintenance_gap_cny'])
            if gap < 0:
                raise ValueError('Net maintenance gap hypothesis must be nonnegative')
        elif basis == 'MATCHED_CAPEX_MINUS_DA_ALREADY_EXPENSED_IN_P':
            capex, da = map(_number, (row['maintenance_capex_cny'], row['matched_da_cny']))
            if min(capex, da) < 0 or overlap > capex:
                raise ValueError('Invalid matched maintenance/DA amounts')
            gap = capex - da
        else:
            raise ValueError('Unsupported maintenance basis')
        # WC excludes cash/customer funds by explicit caller research contract.
        return gap + project - overlap + wc, fund, project, dict(row)


def _distribution(row, year):
    _keys(row, 'year payout_ratio newly_withheld_fraction release_fraction '
          'reserve_transfer_fraction reserve_policy_rationale capacity_mapping_rationale')
    if type(row['year']) is not int or row['year'] != year:
        raise ValueError('Distribution year mismatch')
    _reason(row['reserve_policy_rationale'])
    _reason(row['capacity_mapping_rationale'])
    return tuple(_rate(row[key]) for key in (
        'payout_ratio', 'newly_withheld_fraction', 'release_fraction', 'reserve_transfer_fraction'))


def build_finite_advantage_cash_path(*, opening_state, legacy_profit_rows,
                                   capital_cash_rows, distribution_rows,
                                   fade_policy, terminal_policy=None):
    """Return LOW cash-constrained finite RI research; never approve a company.

    opening_state exact fields: scope/currency/book_equity_cny/cash_cny/
    unremitted_assets_cny/distribution_capacity_cny/cash_floor_cny/
    uncalled_fund_commitment_cny/selected_project_budget_cny/ordinary_shares.
    Capacity is an explicit research proxy, NOT certified legal parent profit.
    legacy_profit_rows = five {year, profit_cny}; no native baseline is edited.
    fade_policy = {cost_of_equity, fade_years, incremental_cash_yield}.
    Capital and distribution rows cover 5+fade_years; exact keys are validated.
    WC must exclude cash/customer funds; matched DA was already expensed in P.
    terminal_policy = {method, rationale, equity_pricing_assumption,
      distribution_constraint_rationale, capital_cash_row, distribution_row}.
    Only explicitly repeated zero-growth/Ke-return/full-payout continuation is
    supported. Reserve treatment still requires its own explicit rationale.
    No default dates, legal capacity, missing zeros or terminal value are inferred.
    """
    _keys(opening_state, 'scope currency book_equity_cny cash_cny unremitted_assets_cny '
          'distribution_capacity_cny cash_floor_cny uncalled_fund_commitment_cny '
          'selected_project_budget_cny ordinary_shares')
    if opening_state['scope'] != SCOPE or opening_state['currency'] != 'CNY':
        raise ValueError('Explicit owner-equivalent CNY research scope required, not group-to-parent mapping')
    _keys(fade_policy, 'cost_of_equity fade_years incremental_cash_yield')
    years = fade_policy['fade_years']
    if type(years) is not int or not 1 <= years <= 100:
        raise ValueError('Explicit finite positive fade_years required')
    horizon = 5 + years
    if (not isinstance(legacy_profit_rows, list) or len(legacy_profit_rows) != 5
            or not isinstance(capital_cash_rows, list) or len(capital_cash_rows) != horizon
            or not isinstance(distribution_rows, list) or len(distribution_rows) != horizon):
        raise ValueError('Five operating profits and complete explicit cash/distribution horizon required')
    profits = []
    for year, row in enumerate(legacy_profit_rows, 1):
        _keys(row, 'year profit_cny')
        if type(row['year']) is not int or row['year'] != year:
            raise ValueError('Legacy profit year mismatch')
        profits.append(_number(row['profit_cny']))
    capital = [_capital(row, year, SCOPE) for year, row in enumerate(capital_cash_rows, 1)]
    distributions = [_distribution(row, year) for year, row in enumerate(distribution_rows, 1)]
    with localcontext() as context:
        context.prec = 48
        ke, cash_yield = map(_number, (fade_policy['cost_of_equity'], fade_policy['incremental_cash_yield']))
        if not 0 < ke < 1 or cash_yield < 0:
            raise ValueError('Invalid Ke/cash yield')
        b, c, u, capacity, floor, fund_remaining, project_remaining, shares = map(_number, (
            opening_state[key] for key in ('book_equity_cny', 'cash_cny', 'unremitted_assets_cny',
                'distribution_capacity_cny', 'cash_floor_cny', 'uncalled_fund_commitment_cny',
                'selected_project_budget_cny', 'ordinary_shares')))
        if b <= 0 or min(c, u, capacity, floor, fund_remaining, project_remaining) < 0 or shares <= 0 or shares != shares.to_integral_value():
            raise ValueError('Invalid opening state')
        a = b - c - u
        if a < 0 or c < floor:
            raise ValueError('Opening residual net equity/cash floor invalid')
        b0, c0 = b, c
        rows, blockers = [], []
        pv_ri = pv_d = Decimal(0)
        roe5 = None
        for year in range(1, horizon + 1):
            n, fund, project, cash_input = capital[year - 1]
            payout, withheld_rate, release_rate, reserve = distributions[year - 1]
            if year <= 5:
                p = profits[year - 1] + cash_yield * (c - c0)
            else:
                if roe5 is None or roe5 < ke:
                    blockers.append('NEGATIVE_EXCESS_RETURN_NOT_ASSUMED_TO_RECOVER_TO_KE')
                    break
                roe = ke + (roe5 - ke) * (1 - Decimal(year - 5) / years)
                p = roe * b
            if p < 0 or b <= 0:
                blockers.append('NONPOSITIVE_BOOK_OR_NEGATIVE_PROFIT_UNSUPPORTED')
                break
            held, released = p * withheld_rate, u * release_rate
            m = p - held + released
            d = payout * p
            ri, discount = p - ke * b, (1 + ke) ** year
            next_b, next_c, next_u = b + p - d, c + m - n - fund - d, u + held - released
            next_a = a + n + fund
            next_capacity = capacity + m - reserve * p - d
            checks = dict(cash_floor=next_c >= floor, distribution_capacity=next_capacity >= 0,
                          fund_budget=fund <= fund_remaining, project_budget=project <= project_remaining,
                          residual_net_equity=next_a >= 0)
            row = dict(year=year, phase='OPERATING_HYPOTHESIS' if year <= 5 else 'TOTAL_OWNER_ROE_FADE_INCLUDING_CASH',
                opening_book_cny=b, profit_cny=p, distribution_cny=d, upstream_funds_cny=m,
                withheld_cny=held, released_cny=released, net_capital_cash_need_cny=n,
                fund_call_cny=fund, closing_book_cny=next_b, closing_cash_cny=next_c,
                closing_unremitted_assets_cny=next_u, residual_net_equity_component_cny=next_a,
                distribution_capacity_proxy_cny=next_capacity, ri_cny=ri, discount_factor=discount,
                pv_ri_cny=ri / discount, pv_distribution_cny=d / discount,
                clean_surplus_residual_cny=next_b-next_c-next_u-next_a,
                capital_cash_input=cash_input, distribution_input=dict(distribution_rows[year - 1]), checks=checks)
            rows.append(row)
            if not all(checks.values()):
                blockers.extend('YEAR_%s_%s' % (year, key.upper()) for key, ok in checks.items() if not ok)
                break
            if year == 5:
                roe5 = p / b
            pv_ri += ri / discount
            pv_d += d / discount
            b, c, u, a, capacity = next_b, next_c, next_u, next_a, next_capacity
            fund_remaining -= fund
            project_remaining -= project
        terminal = dict(status='UNSUPPORTED', terminal_ri_cny=None, reasons=[])
        valuation = dict(usable=False, equity_value_cny=None, per_share_cny=None,
                         pv_explicit_ri_cny=pv_ri, pv_terminal_ri_cny=None,
                         ddm_equity_value_cny=None, ri_ddm_residual_cny=None)
        if not blockers and len(rows) == horizon:
            if terminal_policy is None:
                terminal['reasons'].append('EXPLICIT_TERMINAL_POLICY_MISSING')
            else:
                _keys(terminal_policy, 'method rationale equity_pricing_assumption '
                      'distribution_constraint_rationale capital_cash_row distribution_row')
                for key in ('rationale', 'distribution_constraint_rationale'):
                    _reason(terminal_policy[key])
                n, fund, project, terminal_cash = _capital(terminal_policy['capital_cash_row'], horizon + 1, SCOPE)
                terminal_gap = (
                    _number(terminal_cash['net_maintenance_gap_cny'])
                    if terminal_cash['maintenance_basis'] == 'EXPLICIT_NET_GAP_ASSUMPTION'
                    else _number(terminal_cash['maintenance_capex_cny']) - _number(terminal_cash['matched_da_cny']))
                payout, withheld, release, reserve = _distribution(terminal_policy['distribution_row'], horizon + 1)
                checks = dict(
                    explicit_method=terminal_policy['method'] == 'ZERO_GROWTH_KE_RETURN_FULL_PAYOUT',
                    book_pricing_assumption=terminal_policy['equity_pricing_assumption'] == 'ECONOMIC_BOOK_PRICING_NOT_LIQUIDATION_FACT',
                    normal_return=abs(rows[-1]['profit_cny'] / rows[-1]['opening_book_cny'] - ke) < Decimal('1e-40'),
                    no_unremitted_assets=u == 0, no_unpaid_selected_commitments=fund_remaining == 0 and project_remaining == 0,
                    no_new_funding=fund == 0 and project == 0,
                    net_maintenance_gap_zero=terminal_gap == 0,
                    no_recurring_wc_release_or_investment=_number(terminal_cash['operating_wc_increase_cny']) == 0,
                    net_maintenance_wc_balanced=n == 0,
                    full_funds_conversion=withheld == 0 and release == 0,
                    supported_full_distribution=payout == 1 and reserve == 0,
                    cash_floor=c >= floor, capacity_non_depleting=capacity >= 0)
                terminal.update(checks=checks, policy=dict(terminal_policy), next_profit_cny=ke*b,
                                next_distribution_cny=payout*ke*b,
                                next_cash_cny=c + ke*b*(1-withheld-payout) - n - fund,
                                next_book_cny=b + ke*b*(1-payout))
                terminal['reasons'] = [key for key, ok in checks.items() if not ok]
                if all(checks.values()):
                    terminal.update(status='CONDITIONAL_TERMINAL_SUPPORTED', terminal_ri_cny=Decimal(0))
                    value = b0 + pv_ri
                    ddm = pv_d + b / (1+ke)**horizon
                    if abs(value-ddm) > Decimal('0.00000001'):
                        raise ValueError('RI/DDM clean-surplus cross-check failed')
                    valuation.update(usable=True, equity_value_cny=value, per_share_cny=value/shares,
                                     pv_terminal_ri_cny=Decimal(0), ddm_equity_value_cny=ddm,
                                     ri_ddm_residual_cny=value-ddm)
            blockers.extend('TERMINAL_' + reason for reason in terminal['reasons'])
        return _plain(dict(version=VERSION, status='CONDITIONAL_RESEARCH_VALUATION' if valuation['usable'] else 'VALUATION_UNSUPPORTED',
            scope=SCOPE, confidence='LOW', rows=rows, terminal=terminal, valuation=valuation,
            blockers=blockers, opening_state=dict(opening_state), fade_policy=dict(fade_policy),
            action='no_order', formal_eligibility=False, economic_approval=False, price_admission=False,
            limitations=[
                'M=P-withheld+release is a LOW parent-profit-to-funds mapping, not parent legal profit or CFO.',
                'Residual A=B-C-U is a net-equity component, not verified assets or NAV.',
                'Cash needs are deducted here once; upstream mapping must not already deduct them.',
                'Operating WC excludes cash and customer funds. Other noncash/net financing are explicit zero hypotheses.',
                'Net-gap zero means maintenance and already-expensed noncash charges offset, NOT no maintenance.',
                'Fund/project schedules are explicit research assumptions, not verified current payables or payment dates.',
                'Fade is total owner return including cash/financial assets, not an independent operating forecast.',
                'Capacity/reserve mappings and terminal book pricing are conditional hypotheses, not legal or economic approval.']))
