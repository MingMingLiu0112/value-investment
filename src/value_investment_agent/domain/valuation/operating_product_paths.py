"""Caller-specified product paths into the existing conditional native cash ledger.

No source authentication, default forecast policy, valuation or economic approval.
H1 product weights allocate a TTM research reference, not observed TTM products.
"""
from decimal import Decimal as D, localcontext

from .operating_realization_erosion_v1 import FIELDS
from .source_native_cash_v1 import _number, replay_timing_delay_inputs


POLICY_FIELDS = frozenset({
    'moutai_volume_growth', 'moutai_realization_growth', 'series_volume_growth',
    'series_realization_growth', 'other_revenue_growth', 'cost_ratio',
})
SCENARIOS = ('bear', 'base', 'bull')
ALLOCATION_SCOPE = 'RESEARCH_REFERENCE_ALLOCATION_NOT_OBSERVED_TTM_PRODUCT_REVENUE'


def _plain(value):
    if isinstance(value, D):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def build_product_operating_paths(*, annual, interim, product_revenue_cny, policy, ledger, opening_book):
    """Generate all three five-year paths, then independently replay the full cash.

    Invalid contracts raise ValueError. Economically unsupported fixed dividends
    return UNSUPPORTED without valuation or scenario_inputs, never resized payouts.
    The caller must authenticate source/period/policy identities before calling.
    """
    for statement in (annual, interim):
        if (not isinstance(statement, dict) or set(statement) != FIELDS
                or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                       for pair in statement.values())):
            raise ValueError('Exact current/prior operating statement fields required')
    if not isinstance(product_revenue_cny, dict) or set(product_revenue_cny) != {'moutai', 'series', 'other'}:
        raise ValueError('Exact H1 product revenue fields required')
    if (not isinstance(policy, dict) or set(policy) != set(SCENARIOS)
            or any(not isinstance(policy[name], list) or len(policy[name]) != 5
                   or any(not isinstance(row, dict) or set(row) != POLICY_FIELDS for row in policy[name])
                   for name in SCENARIOS)):
        raise ValueError('Exactly three five-year policies with six explicit fields required')
    with localcontext() as ctx:
        ctx.prec = 48
        a = {key: tuple(map(_number, pair)) for key, pair in annual.items()}
        h = {key: tuple(map(_number, pair)) for key, pair in interim.items()}
        expenses = ('taxes_surcharges', 'selling', 'administration', 'research')
        for statement in (a, h):
            for column in (0, 1):
                revenue, pbt, tax, parent = (statement[key][column] for key in (
                    'operating_revenue', 'profit_before_tax', 'income_tax', 'parent_profit'))
                if (revenue <= 0 or pbt <= 0 or not 0 <= tax < pbt
                        or not 0 < parent <= pbt-tax
                        or any(statement[key][column] < 0 for key in ('cost_of_sales', *expenses))):
                    raise ValueError('Unsupported historical signs or parent attribution')
        ttm = {key: a[key][0]+h[key][0]-h[key][1] for key in FIELDS}
        revenue, pbt, tax, parent, anchor = (ttm[key] for key in (
            'operating_revenue', 'profit_before_tax', 'income_tax', 'parent_profit', 'ex_parent_profit'))
        if (revenue <= 0 or pbt <= 0 or not 0 <= tax < pbt or anchor <= 0
                or not 0 < parent <= pbt-tax
                or any(ttm[key] < 0 for key in ('cost_of_sales', *expenses))):
            raise ValueError('Unsupported TTM profit, costs or ownership')
        products = {key: _number(value) for key, value in product_revenue_cny.items()}
        if min(products.values()) < 0 or sum(products.values()) != h['operating_revenue'][0]:
            raise ValueError('H1 products must reconcile exactly to whole operating revenue, not wine only')
        reference = {key: revenue*products[key]/h['operating_revenue'][0] for key in ('moutai', 'series')}
        # Allocate the final residual explicitly so the research reference adds up.
        if products['other'] == 0:
            reference['series'] = revenue-reference['moutai']
            reference['other'] = D(0)
        else:
            reference['other'] = revenue-sum(reference.values())
        if min(reference.values()) < 0:
            raise ValueError('Product reference allocation has unsupported signs')
        allocation = dict(scope=ALLOCATION_SCOPE, h1_total_revenue_cny=h['operating_revenue'][0],
            ttm_total_revenue_cny=revenue, products={key: dict(
                h1_revenue_cny=products[key], h1_weight=products[key]/h['operating_revenue'][0],
                ttm_reference_revenue_cny=reference[key]) for key in products},
            rounding_residual_assigned_to='series' if products['other'] == 0 else 'other')
        ratios = {key: ttm[key]/revenue for key in expenses}
        selected = revenue-ttm['cost_of_sales']-sum(ttm[key] for key in expenses)
        residual, tax_factor = pbt-selected, 1-tax/pbt
        parent_factor, nonrecurring = parent/(pbt-tax), parent-anchor
        operating = {}
        for name in SCENARIOS:
            previous = dict(reference)
            rows = []
            for year, spec in enumerate(policy[name], 1):
                drivers = {key: _number(value) for key, value in spec.items()}
                if (not 0 <= drivers['cost_ratio'] <= 1
                        or any(drivers[key] <= -1 for key in POLICY_FIELDS if key != 'cost_ratio')):
                    raise ValueError('Product growth must exceed -100%; cost ratio must be within [0,1]')
                amounts = {key: previous[key]*(1+drivers[key+'_volume_growth'])*(
                    1+drivers[key+'_realization_growth']) for key in ('moutai', 'series')}
                amounts['other'] = previous['other']*(1+drivers['other_revenue_growth'])
                rev = sum(amounts.values())
                cost = rev*drivers['cost_ratio']
                charges = {key: rev*ratio for key, ratio in ratios.items()}
                forward_pbt = rev-cost-sum(charges.values())+residual
                profit = forward_pbt*tax_factor*parent_factor-nonrecurring
                rows.append(dict(year=year, opening_product_reference_revenue_cny=dict(previous),
                    product_revenue_cny=amounts, drivers=drivers, revenue=rev, cost=cost,
                    expenses=charges, other_pre_tax_balance=residual, legacy_pre_tax_profit=forward_pbt,
                    effective_tax_rate=1-tax_factor, parent_share=parent_factor,
                    net_parent_nonrecurring_difference=nonrecurring, legacy_ex_parent=profit))
                previous = amounts
            operating[name] = rows
        plan, history = ledger['plan'], ledger['history']
        if (type(plan['horizon']) is not int or plan['horizon'] != 5
                or plan['TIMING_DELAY']['withheld_years'] != [1]
                or any(type(year) is not int for year in plan['TIMING_DELAY']['withheld_years'])
                or history['unit'] != 'CNY'
                or history['scope'] != 'standalone parent, NOT consolidated free cash'):
            raise ValueError('Only original five-year TIMING_DELAY parent scope supported')
        retention, held, q, ke = map(_number, (plan['explicit_retention'],
            plan['TIMING_DELAY']['withheld_fraction'], plan['incremental_parent_cash_yield'], plan['ke']))
        if retention != D('.1') or held != D('.1') or q < 0 or ke <= 0:
            raise ValueError('Inherited retention, delay or return assumptions are unsupported')
        cases = ledger['cases']['TIMING_DELAY']
        if set(cases) != set(SCENARIOS):
            raise ValueError('Exact three-scenario cash baseline required')
        if any(case['branch'] != 'TIMING_DELAY' or case['blockers']
               or any(_number(case[field]) != 0 for field in (
                   'terminal_appropriation', 'terminal_growth', 'terminal_retention', 'terminal_funding_gap'))
               for case in cases.values()):
            raise ValueError('Inherited cash blockers or zero-growth full-payout terminal differ')
        annual_bases = [row for period, row in history['periods'].items()
                        if len(period) == 6 and period.startswith('FY') and period[2:].isdigit()]
        if len(annual_bases) != 1:
            raise ValueError('One explicit annual cash spending basis required')
        floor, budget = map(_number, (cases['bear']['cash_floor'], cases['bear']['project_budget']))
        if (floor != _number(annual_bases[0]['operating_outflows'])/2
                or any(_number(cases[name]['cash_floor']) != floor
                       or _number(cases[name]['project_budget']) != budget for name in SCENARIOS)):
            raise ValueError('Inherited common cash floor or project budget differs')
        book0 = _number(opening_book)
        cash0, parent_book0, parent_re0 = map(_number, (history['ttm']['cash_end'],
            history['ttm']['parent_equity_end'], history['ttm']['parent_retained_profit_end']))
        call = _number(plan['known_uncalled_fund_commitment']['amount_cny'])
        if (call != _number(history['known_uncalled_fund_commitment']['amount_cny'])
                or min(floor, budget, call, cash0, parent_re0) < 0 or min(book0, parent_book0) <= 0):
            raise ValueError('Unsupported opening balances or fund commitment')
        common = dict(historical_ttm=ttm, reference_allocation=allocation, operating_rows=operating,
            scope='CONDITIONAL_PRODUCT_PATHS_NOT_NORMALIZED_OR_ECONOMIC_APPROVAL', action='no_order',
            normalized_parent_profit_cny=None, economic_approval=False,
            limitations=['Product allocation is not observed TTM product revenue.',
                'Volume and realization changes are caller research assumptions; realization includes mix.',
                'TTM expense ratios, finance/other residual, tax and parent share are held by assumption.',
                '90% explicit payout and full-payout zero-growth terminal are inherited hypotheses, not sustainable distributions.'])
        scenarios = {}
        for name in SCENARIOS:
            book, cash, parent_book, parent_re = book0, cash0, parent_book0, parent_re0
            delayed, paid_fund = D(0), D(0)
            cash_rows = []
            for driver in operating[name]:
                year, legacy = driver['year'], driver['legacy_ex_parent']
                income = q*(cash-cash0)
                profit = legacy+income
                withheld, released = (held*profit if year == 1 else D(0)), (delayed if year == 2 else D(0))
                funds = profit-withheld+released
                appropriation = D('.10')*max(D(0), funds)
                planned, fund = (1-retention)*profit, call if year == 1 else D(0)
                capacity = max(D(0), cash+funds-budget/5-fund-floor)
                re_capacity = max(D(0), parent_re+funds-appropriation)
                if profit <= 0 or book <= 0 or planned > capacity or planned > re_capacity:
                    constraint = ('NON_POSITIVE_PROFIT_OR_BOOK' if profit <= 0 or book <= 0 else
                        'PARENT_CASH_CAPACITY' if planned > capacity else 'PARENT_RETAINED_PROFIT_CAPACITY')
                    return _plain(dict(common, status='UNSUPPORTED', failure=dict(scenario=name,
                        constraint=constraint, year=year, profit=profit, planned_dividend=planned,
                        cash_capacity=capacity, retained_profit_capacity=re_capacity,
                        cash_margin=capacity-planned, retained_profit_margin=re_capacity-planned),
                        partial_cash_rows=cash_rows))
                paid_fund += fund
                row = dict(year=year, legacy_profit_before_new_cash_cost=legacy,
                    opening_book=book, opening_parent_cash=cash, opening_delayed_asset=delayed,
                    incremental_parent_cash_income=income, permanent_after_tax_cash_expense=D(0),
                    profit=profit, newly_withheld=withheld, released=released, parent_net_funds=funds,
                    assumed_parent_standalone_profit=funds, statutory_appropriation=appropriation,
                    dividend_planned=planned, dividend_paid=planned, actual_retention=(profit-planned)/profit,
                    cash_capacity=capacity, retained_profit_capacity=re_capacity, project_cash=budget/5,
                    fund_capital_call=fund, fund_asset_at_cost=paid_fund,
                    cash_close=cash+funds-budget/5-fund-planned, delayed_close=delayed+withheld-released,
                    roe=profit/book, book_close=book+profit-planned,
                    parent_equity_close=parent_book+funds-planned,
                    parent_retained_profit_close=parent_re+funds-appropriation-planned,
                    cash_bridge_residual=D(0))
                cash_rows.append(row)
                book, cash, delayed, parent_book, parent_re = (row[key] for key in (
                    'book_close', 'cash_close', 'delayed_close', 'parent_equity_close', 'parent_retained_profit_close'))
            terminal = legacy+q*(cash-cash0)
            if terminal <= 0 or delayed != 0:
                return _plain(dict(common, status='UNSUPPORTED', failure=dict(scenario=name,
                    constraint='NO_POSITIVE_FULL_PAYOUT_TERMINAL', terminal_profit=terminal,
                    terminal_delayed_asset=delayed), partial_cash_rows=cash_rows))
            scenarios[name] = dict(branch='TIMING_DELAY', blockers=[], annual_rows=cash_rows,
                cash_floor=floor, project_budget=budget, terminal_profit=terminal, terminal_cash=cash,
                terminal_delayed_asset=delayed, terminal_book=book, parent_retained_profit_end=parent_re,
                terminal_incremental_cash_income=q*(cash-cash0), terminal_roe=terminal/book,
                terminal_appropriation=D(0), terminal_growth=D(0), terminal_retention=D(0),
                terminal_funding_gap=D(0), terminal_parent_funds=terminal, terminal_assumed_dividend=terminal)
        scenarios = _plain(scenarios)
        inputs = replay_timing_delay_inputs(plan=plan, scenarios=scenarios, opening_book=opening_book, history=history)
        return _plain(dict(common, status='CASH_CONTRACT_REPLAYED_NOT_ECONOMIC_APPROVAL',
            scenarios=scenarios, scenario_inputs=inputs))
