"""Bounded JS1 operating erosion -> unchanged JS2 timing-delay cash contract.

No valuation model, source authentication, probabilities or economic approval.
The mixed wine revenue/volume proxy is not an observed individual selling price.
"""
from copy import deepcopy
from decimal import Decimal as D, localcontext

from .source_native_cash_v1 import _number, replay_timing_delay_inputs


FIELDS = frozenset({'operating_revenue', 'cost_of_sales', 'taxes_surcharges',
    'selling', 'administration', 'research', 'profit_before_tax', 'income_tax',
    'parent_profit', 'ex_parent_profit'})


def build_erosion_bear(*, annual, interim, wine_revenue_yoy_pct, wine_volume_yoy_pct,
                       ledger, opening_book):
    """Five annual compound shocks; H1 cost ratio applies immediately.

    Statement dictionaries contain explicit current/prior decimal pairs. Caller
    must bind/verify official originals. Failed fixed-payout plans have no price.
    Base/bull objects and strings are copied verbatim, not recalculated in place.
    """
    if set(annual) != FIELDS or set(interim) != FIELDS:
        raise ValueError('Exact existing JS1 statement fields required')
    if any(not isinstance(pair, (list, tuple)) or len(pair) != 2
           for pair in [*annual.values(), *interim.values()]):
        raise ValueError('Explicit current/comparative pairs required')
    with localcontext() as ctx:
        ctx.prec = 48
        a = {key: tuple(map(_number, pair)) for key, pair in annual.items()}
        h = {key: tuple(map(_number, pair)) for key, pair in interim.items()}
        ttm = {key: a[key][0]+h[key][0]-h[key][1] for key in FIELDS}
        revenue, pbt, tax, parent, anchor = (ttm[key] for key in
            ('operating_revenue', 'profit_before_tax', 'income_tax', 'parent_profit', 'ex_parent_profit'))
        ry, vy = _number(wine_revenue_yoy_pct)/100, _number(wine_volume_yoy_pct)/100
        if (revenue <= 0 or pbt <= 0 or not 0 <= tax < pbt or anchor <= 0
                or not 0 < parent <= pbt-tax or ry <= -1 or vy <= -1
                or h['operating_revenue'][0] <= 0):
            raise ValueError('Unsupported profit, ownership or mixed proxy inputs')
        factor = (1+ry)/(1+vy)
        cost_ratio = h['cost_of_sales'][0]/h['operating_revenue'][0]
        if not 0 < factor < 1 or not 0 <= cost_ratio <= 1:
            raise ValueError('This version requires erosion and a supported H1 cost ratio')
        expenses = ('taxes_surcharges', 'selling', 'administration', 'research')
        if any(ttm[key] < 0 for key in ('cost_of_sales', *expenses)):
            raise ValueError('Negative operating cost scope unsupported')
        ratios = {key: ttm[key]/revenue for key in expenses}
        selected0 = revenue-ttm['cost_of_sales']-sum(ttm[key] for key in expenses)
        tax_factor, parent_factor = 1-tax/pbt, parent/(pbt-tax)
        nonrecurring = parent-anchor
        operating = []
        for year in range(1, 6):
            rev = revenue*factor**year
            cost = rev*cost_ratio
            charges = {key: rev*ratio for key, ratio in ratios.items()}
            forward_pbt = pbt+rev-cost-sum(charges.values())-selected0
            profit = forward_pbt*tax_factor*parent_factor-nonrecurring
            operating.append(dict(year=year, revenue=rev, cost=cost,
                expenses=charges, legacy_pre_tax_profit=forward_pbt, legacy_ex_parent=profit))
        plan, history = ledger['plan'], ledger['history']
        if (type(plan['horizon']) is not int or plan['horizon'] != 5
                or plan['TIMING_DELAY']['withheld_years'] != [1]
                or type(plan['TIMING_DELAY']['withheld_years'][0]) is not int
                or history['unit'] != 'CNY'
                or history['scope'] != 'standalone parent, NOT consolidated free cash'):
            raise ValueError('Only inherited JS2 single-delay contract supported')
        retention, held, q = map(_number, (plan['explicit_retention'],
            plan['TIMING_DELAY']['withheld_fraction'], plan['incremental_parent_cash_yield']))
        if (retention, held) != (D('.1'), D('.1')) or q < 0:
            raise ValueError('JS2 payout, remittance and incremental return must remain unchanged')
        cases = deepcopy(ledger['cases']['TIMING_DELAY'])
        if set(cases) != {'bear', 'base', 'bull'}:
            raise ValueError('Exact three-scenario baseline required')
        old = cases['bear']
        floor, budget = _number(old['cash_floor']), _number(old['project_budget'])
        if (floor != _number(history['periods']['FY2025']['operating_outflows'])/2
                or any(_number(cases[n]['project_budget']) != budget for n in cases)
                or any(_number(cases[n]['cash_floor']) != floor for n in cases)):
            raise ValueError('Inherited common budget/floor identity mismatch')
        cash0 = cash = _number(history['ttm']['cash_end'])
        book, mb, re = map(_number, (opening_book, history['ttm']['parent_equity_end'],
                                    history['ttm']['parent_retained_profit_end']))
        call = _number(plan['known_uncalled_fund_commitment']['amount_cny'])
        if (call != _number(history['known_uncalled_fund_commitment']['amount_cny'])
                or min(floor, budget, call, cash, re) < 0 or min(book, mb) <= 0):
            raise ValueError('Unsupported opening balances or commitments')
        delayed, paid = D(0), D(0)
        rows = []
        for driver in operating:
            year, legacy = driver['year'], driver['legacy_ex_parent']
            income = q*(cash-cash0)
            profit = legacy+income
            withheld, released = (held*profit if year == 1 else D(0)), (delayed if year == 2 else D(0))
            funds = profit-withheld+released
            appropriation = D('.1')*max(D(0), funds)
            dividend = (1-retention)*profit
            fund = call if year == 1 else D(0)
            capacity = max(D(0), cash+funds-budget/5-fund-floor)
            re_capacity = max(D(0), re+funds-appropriation)
            if profit <= 0 or book <= 0 or dividend > capacity or dividend > re_capacity:
                constraint = ('NON_POSITIVE_PROFIT_OR_BOOK' if profit <= 0 or book <= 0
                    else 'PARENT_CASH_CAPACITY' if dividend > capacity else 'PARENT_RETAINED_PROFIT_CAPACITY')
                return dict(status='UNSUPPORTED', operating_rows=operating, annual_rows=rows,
                    failure=dict(constraint=constraint, year=year, profit=profit, opening_book=book,
                        planned_dividend=dividend, cash_capacity=capacity,
                        retained_profit_capacity=re_capacity, cash_margin=capacity-dividend,
                        retained_profit_margin=re_capacity-dividend), action='no_order')
            paid += fund
            row = dict(year=year, legacy_profit_before_new_cash_cost=legacy,
                opening_book=book, opening_parent_cash=cash, opening_delayed_asset=delayed,
                incremental_parent_cash_income=income, permanent_after_tax_cash_expense=D(0),
                profit=profit, newly_withheld=withheld, released=released,
                parent_net_funds=funds, assumed_parent_standalone_profit=funds,
                statutory_appropriation=appropriation, dividend_planned=dividend,
                dividend_paid=dividend, actual_retention=(profit-dividend)/profit,
                cash_capacity=capacity, retained_profit_capacity=re_capacity,
                project_cash=budget/5, fund_capital_call=fund, fund_asset_at_cost=paid,
                cash_close=cash+funds-budget/5-fund-dividend, delayed_close=delayed+withheld-released,
                roe=profit/book, book_close=book+profit-dividend,
                parent_equity_close=mb+funds-dividend,
                parent_retained_profit_close=re+funds-appropriation-dividend,
                cash_bridge_residual=D(0))
            rows.append(row)
            book, cash, delayed, mb, re = (row[key] for key in
                ('book_close', 'cash_close', 'delayed_close', 'parent_equity_close', 'parent_retained_profit_close'))
        terminal = operating[-1]['legacy_ex_parent']+q*(cash-cash0)
        if terminal <= 0 or delayed != 0:
            return dict(status='UNSUPPORTED', operating_rows=operating, annual_rows=rows,
                failure=dict(constraint='NO_POSITIVE_FULL_PAYOUT_TERMINAL', terminal_profit=terminal,
                             terminal_delayed_asset=delayed), action='no_order')
        bear = dict(branch='TIMING_DELAY', blockers=[], annual_rows=rows, cash_floor=floor,
            project_budget=budget, terminal_profit=terminal, terminal_cash=cash,
            terminal_delayed_asset=delayed, terminal_book=book, parent_retained_profit_end=re,
            terminal_incremental_cash_income=q*(cash-cash0), terminal_roe=terminal/book,
            terminal_appropriation=D(0), terminal_growth=D(0), terminal_retention=D(0),
            terminal_funding_gap=D(0), terminal_parent_funds=terminal, terminal_assumed_dividend=terminal)
        # Decimal strings are the native contract, including all calculated rows.
        def strings(value):
            if isinstance(value, D): return str(value)
            if isinstance(value, dict): return {k: strings(v) for k, v in value.items()}
            if isinstance(value, list): return [strings(v) for v in value]
            return value
        cases['bear'] = strings(bear)
        inputs = replay_timing_delay_inputs(plan=plan, scenarios=cases, history=history, opening_book=opening_book)
        assert cases['base'] == ledger['cases']['TIMING_DELAY']['base']
        assert cases['bull'] == ledger['cases']['TIMING_DELAY']['bull']
        return dict(status='CASH_CONTRACT_REPLAYED_NOT_ECONOMIC_APPROVAL',
            operating_rows=strings(operating), mixed_realization_factor=str(factor),
            h1_cost_ratio=str(cost_ratio), scenarios=cases, scenario_inputs=inputs,
            historical_ttm=strings(ttm), action='no_order')
