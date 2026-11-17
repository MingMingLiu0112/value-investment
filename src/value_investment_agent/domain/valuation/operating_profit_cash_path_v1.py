"""Explicit annual earnings adapter to existing v4 cash and terminal arithmetic.

No evidence admission, annualisation, normalization or default economic inputs.
Annual earnings exclude new-capital returns added by the declared v4 mechanism.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext

from .signed_parent_profit import build_signed_parent_profit_path
from . import joint_capital_cash_path_v4 as v4

VERSION = 'operating-profit-cash-path-v1'
PROFIT_BASIS = 'LEGACY_PARENT_PROFIT_EXCLUDES_NEW_CAPITAL_RETURNS'
CASH_FIELDS = frozenset(('target_payout_ratio accessible_profit_ratio reserve_ratio '
    'net_maintenance_cash_cny operating_wc_cash_cny commitment_cash_cny').split())
OPENING_FIELDS = frozenset(('as_of scope currency book_equity_cny cash_cny unremitted_cny '
    'distribution_capacity_cny operating_capital_cny productive_capital_cny '
    'cash_floor_cny ordinary_shares').split())
ANNUAL_FIELDS = frozenset(('year period_start period_end scope currency group_pbt_cny '
    'tax_assumption signed_nci_cny cash_policy').split())
CAPITAL_FIELDS = frozenset(('operating_allocation new_operating_return new_liquidity_return').split())
TERMINAL_FIELDS = v4.TERMINAL_FIELDS | frozenset(('terminal_mechanism terminal_start_year '
    'first_distribution_timing legacy_profit_dynamics commitment_occurrences '
    'restricted_cash_release_cny restricted_cash_release_year convergence_tolerance_cny max_tail_years').split())


def _date(value):
    if not isinstance(value, str):
        raise ValueError('EXACT_CALENDAR_DATE_REQUIRED')
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError('EXACT_CALENDAR_DATE_REQUIRED')
    return result


def compile_operating_profit_cash_path(*, opening_state, annual_rows, capital_policy,
                                      terminal_policy, cost_of_equity, profit_basis):
    """Compile ten consecutive complete years, no half-year inference.

    opening_state has OPENING_FIELDS; annual_rows has ten ANNUAL_FIELDS records.
    Optional period_basis is FY or ROLLING_FULL_YEAR, identical across all rows.
    Without it the retained contract is FY. Rolling years start on a month-first
    and end one day before the next anniversary (including July--June).
    Annual scope is consolidated; opening/cash-policy scope is v4.SCOPE, CNY.
    cash_policy has CASH_FIELDS plus explicit scope/currency. Tax assumption is
    {basis: amount_cny|effective_rate, value: decimal string}. No historical NCI
    ratio, impairment addback or recurring-income adjustment is inferred.
    Returns v4 typed scenario, ledger and terminal valuation; callers supply
    QualityCompounderFacts to the existing v4 scenario_calculation themselves.
    """
    v4._keys(opening_state, OPENING_FIELDS)
    v4._keys(capital_policy, CAPITAL_FIELDS)
    v4._keys(terminal_policy, TERMINAL_FIELDS)
    if profit_basis != PROFIT_BASIS:
        raise ValueError('EXPLICIT_LEGACY_PROFIT_BASIS_REQUIRED')
    if opening_state['scope'] != v4.SCOPE or opening_state['currency'] != 'CNY':
        raise ValueError('OWNER_EQUIVALENT_CNY_OPENING_REQUIRED')
    opening_day = _date(opening_state['as_of'])
    if type(annual_rows) is not list or len(annual_rows) != 10:
        raise ValueError('TEN_EXPLICIT_ANNUAL_ROWS_REQUIRED')
    if (terminal_policy['terminal_mechanism'] != 'recursive_capital_use_and_owner_distribution_v2'
            or type(terminal_policy['terminal_start_year']) is not int or terminal_policy['terminal_start_year'] != 11
            or terminal_policy['first_distribution_timing'] != 'end_of_terminal_year_1'
            or terminal_policy['legacy_profit_dynamics'] != 'constant_after_profit_scale_transition'):
        raise ValueError('SUPPORTED_V4_TERMINAL_POLICY_REQUIRED')
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        amounts = {key: v4._number(value) for key, value in opening_state.items()
                   if key not in {'as_of', 'scope', 'currency'}}
        book, cash, unremitted, capacity, operating, productive, floor, shares = (
            amounts[key] for key in ('book_equity_cny', 'cash_cny', 'unremitted_cny',
            'distribution_capacity_cny', 'operating_capital_cny', 'productive_capital_cny',
            'cash_floor_cny', 'ordinary_shares'))
        if (book <= 0 or shares <= 0 or shares != shares.to_integral_value()
                or min(cash, unremitted, capacity, operating, productive, floor) < 0
                or cash < floor or productive > operating or book != cash + unremitted + operating):
            raise ValueError('INVALID_OPENING_CAPITAL_IDENTITY')
        allocation, op_return, liquidity_return = (v4._rate(capital_policy[key]) for key in (
            'operating_allocation', 'new_operating_return', 'new_liquidity_return'))
        ke = v4._number(cost_of_equity)
        if not 0 < ke < 1:
            raise ValueError('COST_OF_EQUITY_OUT_OF_RANGE')
        policies, pbts, taxes, ncis = [], [], [], []
        previous_end = opening_day
        period_basis = None
        for year, raw in enumerate(annual_rows, 1):
            v4._keys(raw, ANNUAL_FIELDS | ({'period_basis'} if isinstance(raw, dict) and 'period_basis' in raw else set()))
            basis = raw.get('period_basis', 'FY')
            if basis not in {'FY', 'ROLLING_FULL_YEAR'} or (period_basis is not None and basis != period_basis):
                raise ValueError('CONSISTENT_FULL_YEAR_BASIS_REQUIRED')
            period_basis = basis
            start, end = _date(raw['period_start']), _date(raw['period_end'])
            if (type(raw['year']) is not int or raw['year'] != year
                    or start != previous_end + timedelta(days=1)
                    or start.day != 1 or (basis == 'FY' and start.month != 1)
                    or end != date(start.year + 1, start.month, 1) - timedelta(days=1)):
                raise ValueError('CONTIGUOUS_FULL_ANNUAL_PERIODS_REQUIRED')
            previous_end = end
            if raw['scope'] != 'consolidated' or raw['currency'] != 'CNY':
                raise ValueError('CONSOLIDATED_CNY_EARNINGS_REQUIRED')
            v4._keys(raw['cash_policy'], CASH_FIELDS | {'scope', 'currency'})
            if raw['cash_policy']['scope'] != v4.SCOPE or raw['cash_policy']['currency'] != 'CNY':
                raise ValueError('OWNER_EQUIVALENT_CNY_CASH_POLICY_REQUIRED')
            v4._keys(raw['tax_assumption'], {'basis', 'value'})
            v4._number(raw['tax_assumption']['value'])
            pbts.append(v4._number(raw['group_pbt_cny']))
            ncis.append(v4._number(raw['signed_nci_cny']))
            taxes.append(deepcopy(raw['tax_assumption']))
            policies.append(v4._cash_policy(raw['cash_policy']))
        earnings = build_signed_parent_profit_path(years=list(range(1, 11)), group_pbt_cny=pbts,
            tax_assumptions=taxes, signed_nci_cny=ncis, currency='CNY')
        state = dict(book=book, cash=cash, unremitted=unremitted, capacity=capacity,
                     operating=operating, productive=productive)
        rows = []
        for year, (earned, policy, raw) in enumerate(zip(earnings['rows'], policies, annual_rows), 1):
            legacy = Decimal(earned['parent_profit_cny'])
            operating_profit = state['productive'] * op_return
            liquidity_profit = (state['cash'] - cash) * liquidity_return
            row, state = v4._step(year=year, profit=legacy + operating_profit + liquidity_profit,
                state=state, policy=policy, allocation=allocation, floor=floor)
            if row['funding_shortfall'] or min(state.values()) < 0:
                raise ValueError('ANNUAL_CASH_OR_CAPITAL_SHORTFALL')
            row.update(period_start=raw['period_start'], period_end=raw['period_end'],
                period_basis=period_basis,
                earnings_bridge=earned, legacy_parent_profit=legacy,
                new_operating_profit=operating_profit, new_liquidity_profit=liquidity_profit)
            rows.append(row)
        scale = v4._number(terminal_policy['profit_scale'])
        if scale <= 0:
            raise ValueError('POSITIVE_TERMINAL_PROFIT_SCALE_REQUIRED')
        terminal_cash = v4._cash_policy(terminal_policy)
        contract = v4.TerminalEconomicContract(opening_book=state['book'], opening_cash=state['cash'],
            opening_unremitted=state['unremitted'], opening_distribution_capacity=state['capacity'],
            opening_operating_capital=state['operating'], opening_productive_capital=state['productive'],
            opening_cash_reference=cash, cash_floor=floor, legacy_profit=rows[-1]['legacy_parent_profit'] * scale,
            operating_allocation=allocation, productive_marginal_return=op_return, liquidity_return=liquidity_return,
            policy=tuple(sorted(terminal_cash.items())), commitment_occurrences=terminal_policy['commitment_occurrences'],
            restricted_cash_release_cny=v4._number(terminal_policy['restricted_cash_release_cny']),
            restricted_cash_release_year=terminal_policy['restricted_cash_release_year'],
            convergence_tolerance_cny=v4._number(terminal_policy['convergence_tolerance_cny']),
            max_tail_years=terminal_policy['max_tail_years'], rationale=terminal_policy['rationale'])
        terminal_value = v4.value_terminal_economic_contract(contract, ke)
        terminal = terminal_value['first_row']
        from ...valuation_models.residual_income_path_v4 import ResidualIncomePathScenarioInputs
        scenario = ResidualIncomePathScenarioInputs(cost_of_equity=ke,
            forecast_roes=tuple(row['forecast_roe'] for row in rows),
            forecast_retentions=tuple(row['retention'] for row in rows),
            terminal_roe=terminal['forecast_roe'], terminal_growth=terminal['retention'] * terminal['forecast_roe'],
            currency='CNY', terminal_economic_contract=contract)
        return dict(version=VERSION, action='no_order', status='CONDITIONAL_RESEARCH_NOT_APPROVED',
            scope=v4.SCOPE, currency='CNY', profit_basis=profit_basis, formal_eligibility=False,
            opening_state=deepcopy(opening_state), rows=rows, earnings_bridge=earnings,
            forecast_roe=scenario.forecast_roes, forecast_retentions=scenario.forecast_retentions,
            terminal=terminal, terminal_economic_contract=contract, terminal_valuation=terminal_value,
            typed_scenario=scenario, funding_status='FUNDED',
            distribution_constraint_years=[row['year'] for row in rows if row['distribution'] < row['target_distribution']],
            limitations=['Explicit annual hypotheses, not annualized half-year facts or normalized earnings.',
                'Legacy earnings exclude the separately added new-capital returns; caller must prove this boundary.',
                'Owner-equivalent cash and capacity are research assumptions, not legal parent cash.',
                'V4 terminal accounting growth is diagnostic, not economic growth authority.',
                'No approval, current price, source admission or real-input acceptance.'])
