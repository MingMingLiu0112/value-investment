"""V4 owner-equivalent cash path with a proved analytical terminal contract.

Financial inputs are plain Decimal strings; years alone are integers. Historical
PBT retains the residual beyond selected costs/expenses. Tax and attribution are
held constant; nonrecurring profit is excluded. DA is an anchor, not a cash
add-back: net maintenance means cash AFTER already-expensed DA.

Book = operating + liquidity + unremitted capital. Cash equals liquidity capital.
Mandatory spending moves cash into residual operating capital, without invented
returns. Only discretionary productive capital earns new_operating_return.
Liquidity yield applies to changes from opening cash, avoiding double counting
historical income. Unremitted assets have no implicit release or yield.

Capacity is an accounting hypothesis, not certified legal parent profit. Reserve
transfers constrain capacity, not cash. Terminal policy is independent of annual
commitments. Retention times book ROE is diagnostic only. Value requires a
supported exact post-forecast regime; discounted book is not a cash-error bound.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import re


SCOPE = 'ordinary_owner_equivalent_cash_mapping'
HISTORICAL_FIELDS = frozenset(('scope currency revenue cost surcharges selling admin research '
    'pre_tax_profit tax parent_profit nonrecurring da opening_cash '
    'opening_distribution_capacity cash_floor').split())
DRIVER_FIELDS = frozenset('years operating_allocation new_operating_return new_liquidity_return'.split())
ANNUAL_FIELDS = frozenset(('year revenue_growth cost_ratio target_payout_ratio '
    'accessible_profit_ratio net_maintenance_cash_cny operating_wc_cash_cny '
    'commitment_cash_cny reserve_ratio').split())
TERMINAL_FIELDS = frozenset(('net_maintenance_cash_cny operating_wc_cash_cny '
    'commitment_cash_cny accessible_profit_ratio target_payout_ratio reserve_ratio '
    'profit_scale rationale').split())
_EXPENSES = ('surcharges', 'selling', 'admin', 'research')
_ZERO = Decimal('0')


@dataclass(frozen=True)
class TerminalEconomicContract:
    """Year-ten state plus the explicit post-forecast capital-use mechanism."""

    opening_book: Decimal
    opening_cash: Decimal
    opening_unremitted: Decimal
    opening_distribution_capacity: Decimal
    opening_operating_capital: Decimal
    opening_productive_capital: Decimal
    opening_cash_reference: Decimal
    cash_floor: Decimal
    legacy_profit: Decimal
    operating_allocation: Decimal
    productive_marginal_return: Decimal
    liquidity_return: Decimal
    policy: tuple[tuple[str, Decimal], ...]
    commitment_occurrences: int | None
    restricted_cash_release_cny: Decimal
    restricted_cash_release_year: int | None
    convergence_tolerance_cny: Decimal
    max_tail_years: int
    rationale: str

    def __post_init__(self):
        decimal_fields = (
            self.opening_book, self.opening_cash, self.opening_unremitted,
            self.opening_distribution_capacity, self.opening_operating_capital,
            self.opening_productive_capital, self.opening_cash_reference,
            self.cash_floor, self.legacy_profit, self.operating_allocation,
            self.productive_marginal_return, self.liquidity_return,
            self.restricted_cash_release_cny, self.convergence_tolerance_cny,
            *(amount for _, amount in self.policy),
        )
        if any(not isinstance(value, Decimal) or not value.is_finite()
               for value in decimal_fields):
            raise ValueError('Terminal contract values must be finite Decimals')
        if (self.opening_book <= 0 or min(
                self.opening_cash, self.opening_unremitted,
                self.opening_distribution_capacity, self.opening_operating_capital,
                self.opening_productive_capital, self.cash_floor,
                self.restricted_cash_release_cny) < 0):
            raise ValueError('Terminal capital balances must be nonnegative')
        if abs(self.opening_book - self.opening_cash - self.opening_unremitted
                - self.opening_operating_capital) > self.convergence_tolerance_cny:
            raise ValueError('Terminal opening capital identity is inconsistent')
        if not 0 <= self.opening_productive_capital <= self.opening_operating_capital:
            raise ValueError('Productive capital must stay inside operating capital')
        if not 0 <= self.operating_allocation <= 1:
            raise ValueError('Terminal operating allocation must be in [0, 1]')
        if any(not 0 <= value <= 1 for value in (
                self.productive_marginal_return, self.liquidity_return)):
            raise ValueError('Terminal capital returns must be in [0, 1]')
        policy = dict(self.policy)
        expected = {'target_payout_ratio', 'accessible_profit_ratio', 'reserve_ratio',
            'net_maintenance_cash_cny', 'operating_wc_cash_cny',
            'commitment_cash_cny'}
        if set(policy) != expected:
            raise ValueError('Exact terminal cash policy required')
        if any(not 0 <= policy[key] <= 1 for key in (
                'target_payout_ratio', 'accessible_profit_ratio', 'reserve_ratio')):
            raise ValueError('Terminal policy ratios must be in [0, 1]')
        if any(policy[key] < 0 for key in (
                'net_maintenance_cash_cny', 'operating_wc_cash_cny',
                'commitment_cash_cny')):
            raise ValueError('Recurring terminal cash needs must be nonnegative')
        if (self.commitment_occurrences is not None
                and (type(self.commitment_occurrences) is not int
                     or self.commitment_occurrences < 0)):
            raise ValueError('Commitment occurrences must be nonnegative or null')
        if ((self.restricted_cash_release_cny == 0)
                != (self.restricted_cash_release_year is None)):
            raise ValueError('Restricted cash release amount and year must coexist')
        if (self.restricted_cash_release_year is not None
                and (type(self.restricted_cash_release_year) is not int
                     or self.restricted_cash_release_year < 1)):
            raise ValueError('Restricted release year must be positive')
        if self.convergence_tolerance_cny <= 0:
            raise ValueError('Positive absolute value-error tolerance required')
        if type(self.max_tail_years) is not int or not 1 <= self.max_tail_years <= 10000:
            raise ValueError('max_tail_years must be in [1, 10000]')
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError('Terminal rationale is required')


def _advance_terminal(contract, state, year):
    policy = dict(contract.policy)
    if (contract.commitment_occurrences is not None
            and year > contract.commitment_occurrences):
        policy['commitment_cash_cny'] = _ZERO
    release = (_ZERO if contract.restricted_cash_release_year != year
        else contract.restricted_cash_release_cny)
    if release:
        if release > state['unremitted']:
            raise ValueError('Restricted release exceeds the bound unremitted balance')
        state = dict(state)
        state['cash'] += release
        state['unremitted'] -= release
    productive_profit = state['productive'] * contract.productive_marginal_return
    liquidity_profit = ((state['cash'] - contract.opening_cash_reference)
        * contract.liquidity_return)
    profit = contract.legacy_profit + productive_profit + liquidity_profit
    row, next_state = _step(year=10 + year, profit=profit, state=state,
        policy=policy, allocation=contract.operating_allocation,
        floor=contract.cash_floor)
    row.update(legacy_parent_profit=contract.legacy_profit,
        new_operating_profit=productive_profit,
        new_liquidity_profit=liquidity_profit,
        restricted_cash_release_cny=release)
    return row, next_state


def _terminal_policy_for_year(contract, year):
    policy = dict(contract.policy)
    if (contract.commitment_occurrences is not None
            and year > contract.commitment_occurrences):
        policy['commitment_cash_cny'] = _ZERO
    return policy


def _exact_tail_from_state(contract, state, year, required_return):
    """Prove and value one of the two supported continuing regimes."""
    next_year = year + 1
    row, next_state = _advance_terminal(contract, state, next_year)
    if row['funding_shortfall']:
        raise ValueError('Terminal mechanism has an unfunded cash requirement')

    if (next_state['productive'] == state['productive']
            and next_state['cash'] == state['cash']
            and next_state['capacity'] >= state['capacity']):
        return dict(
            valuation_method='exact_static_owner_distribution_perpetuity',
            equity_value=row['distribution'] / required_return,
            first_analytical_row=row,
        )

    policy = _terminal_policy_for_year(contract, next_year)
    payout = policy['target_payout_ratio']
    allocation = contract.operating_allocation
    if (row['distribution'] != row['target_distribution']
            or row['discretionary_operating_addition'] != row['retained'] * allocation
            or payout + policy['reserve_ratio'] > 1):
        return None
    cash_reinvestment = (policy['accessible_profit_ratio'] - payout
        - allocation * (1 - payout))
    if cash_reinvestment < 0:
        return None
    mandatory = sum(policy[key] for key in (
        'net_maintenance_cash_cny', 'operating_wc_cash_cny',
        'commitment_cash_cny'))
    if cash_reinvestment * row['profit'] < mandatory:
        return None
    growth = (contract.productive_marginal_return * allocation * (1 - payout)
        + contract.liquidity_return * cash_reinvestment)
    liquidity_drain = contract.liquidity_return * mandatory
    if growth >= required_return:
        raise ValueError('Terminal target-payout regime is not value-convergent')
    if growth == 0:
        if liquidity_drain:
            return None
        stationary_profit = row['profit']
        tail = payout * row['profit'] / required_return
    else:
        stationary_profit = liquidity_drain / growth
        if row['profit'] < stationary_profit:
            return None
        tail = payout * (stationary_profit / required_return
            + (row['profit'] - stationary_profit) / (required_return - growth))
    return dict(
        valuation_method='exact_affine_target_payout_perpetuity',
        equity_value=tail,
        first_analytical_row=row,
        profit_growth_coefficient=growth,
        stationary_profit=stationary_profit,
    )


def value_terminal_economic_contract(contract, required_return):
    """Value declared owner cash with a proved analytical tail."""
    if not isinstance(contract, TerminalEconomicContract):
        raise ValueError('Typed terminal economic contract required')
    if (not isinstance(required_return, Decimal) or not required_return.is_finite()
            or not _ZERO < required_return < 1):
        raise ValueError('Finite required return in (0, 1) required')
    state = dict(book=contract.opening_book, cash=contract.opening_cash,
        unremitted=contract.opening_unremitted,
        capacity=contract.opening_distribution_capacity,
        operating=contract.opening_operating_capital,
        productive=contract.opening_productive_capital)
    with localcontext() as context:
        context.prec = 48
        distribution_value = _ZERO
        residual_value = contract.opening_book
        first_row = None
        restricted_release_consumed = _ZERO
        last_scheduled_event_year = max(
            contract.commitment_occurrences or 0,
            contract.restricted_cash_release_year or 0,
        )
        for year in range(1, contract.max_tail_years + 1):
            row, state = _advance_terminal(contract, state, year)
            if row['funding_shortfall']:
                raise ValueError('Terminal mechanism has an unfunded cash requirement')
            if first_row is None:
                first_row = row
            restricted_release_consumed += row['restricted_cash_release_cny']
            discount = (1 + required_return) ** year
            distribution_value += row['distribution'] / discount
            residual_income = row['profit'] - required_return * row['opening_book']
            residual_value += residual_income / discount
            discounted_book = row['closing_book'] / discount
            if year < last_scheduled_event_year:
                continue
            tail = _exact_tail_from_state(contract, state, year, required_return)
            if tail is None:
                continue
            tail_at_year = tail['equity_value']
            distribution_equity = distribution_value + tail_at_year / discount
            residual_equity = (residual_value
                + (tail_at_year - row['closing_book']) / discount)
            difference = residual_equity - distribution_equity
            arithmetic_tolerance = max(
                Decimal('1e-18'), abs(distribution_equity) * Decimal('1e-36'))
            if abs(difference) > arithmetic_tolerance:
                raise ValueError('Terminal clean-surplus bridge failed')
            return dict(version='terminal-economic-contract-v2',
                mechanism='recursive_capital_use_and_owner_distribution',
                valuation_method=tail['valuation_method'],
                equity_value=distribution_equity,
                distribution_value=distribution_equity,
                residual_income_value=residual_equity,
                clean_surplus_bridge_residual=difference,
                convergence_residual=_ZERO,
                absolute_error_bound_cny=_ZERO,
                relative_error_bound=_ZERO,
                requested_absolute_error_tolerance_cny=contract.convergence_tolerance_cny,
                last_scheduled_event_year=last_scheduled_event_year,
                restricted_cash_release_consumed_cny=restricted_release_consumed,
                commitment_occurrences_consumed=(
                    year if contract.commitment_occurrences is None
                    else min(year, contract.commitment_occurrences)),
                years_evaluated=year, first_distribution=first_row['distribution'],
                first_row=first_row, last_row=row,
                analytical_first_row=tail['first_analytical_row'],
                discounted_book_at_tail_start=discounted_book,
                action='no_order')
        raise ValueError(
            'Terminal economic path has no supported exact tail within max_tail_years')


def _keys(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise ValueError('Exact joint cash fields required')


def _number(value):
    if type(value) is not str or re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value) is None:
        raise ValueError('Finite plain Decimal strings required')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Finite plain Decimal strings required')
    return result


def _rate(value):
    number = _number(value)
    if not 0 <= number <= 1:
        raise ValueError('Ratio must be in [0, 1]')
    return number


def _cash_policy(raw):
    values = {k: _rate(raw[k]) for k in (
        'target_payout_ratio', 'accessible_profit_ratio', 'reserve_ratio')}
    for k in ('net_maintenance_cash_cny', 'operating_wc_cash_cny', 'commitment_cash_cny'):
        values[k] = _number(raw[k])
    if min(values['net_maintenance_cash_cny'], values['commitment_cash_cny']) < 0:
        raise ValueError('Maintenance and commitments must be nonnegative')
    return values


def _step(*, year, profit, state, policy, allocation, floor):
    if profit <= 0:
        raise ValueError('Positive forecast profit required by the RI path contract')
    accessible = profit * policy['accessible_profit_ratio']
    withheld = profit - accessible
    mandatory = sum(policy[k] for k in (
        'net_maintenance_cash_cny', 'operating_wc_cash_cny', 'commitment_cash_cny'))
    cash_before_distribution = state['cash'] + accessible - mandatory
    cash_limit = max(_ZERO, cash_before_distribution - floor)
    reserve = profit * policy['reserve_ratio']
    capacity_limit = state['capacity'] + profit - reserve
    target = profit * policy['target_payout_ratio']
    distribution = min(target, cash_limit, capacity_limit)
    retained = profit - distribution
    # Discretionary investment is funded only after the constrained dividend.
    operating_addition = min(retained * allocation,
        max(_ZERO, cash_before_distribution - distribution - floor))
    cash_close = cash_before_distribution - distribution - operating_addition
    book_close = state['book'] + retained
    unremitted_close = state['unremitted'] + withheld
    operating_close = state['operating'] + mandatory + operating_addition
    capacity_close = capacity_limit - distribution
    shortfall = max(_ZERO, floor - cash_close)
    row = dict(year=year, profit=profit, opening_book=state['book'],
        opening_cash=state['cash'], opening_unremitted=state['unremitted'],
        opening_distribution_capacity=state['capacity'],
        opening_operating_capital=state['operating'], opening_liquidity_capital=state['cash'],
        forecast_roe=profit / state['book'], target_distribution=target,
        accessible_profit=accessible, newly_unremitted=withheld,
        net_maintenance_cash_cny=policy['net_maintenance_cash_cny'],
        operating_wc_cash_cny=policy['operating_wc_cash_cny'],
        commitment_cash_cny=policy['commitment_cash_cny'],
        mandatory_cash=mandatory, cash_distribution_limit=cash_limit,
        capacity_distribution_limit=capacity_limit, reserve_transfer=reserve,
        distribution=distribution, retained=retained, retention=retained / profit,
        discretionary_operating_addition=operating_addition,
        closing_productive_operating_capital=state['productive'] + operating_addition,
        closing_operating_capital=operating_close, closing_liquidity_capital=cash_close,
        closing_cash=cash_close, closing_book=book_close,
        closing_unremitted=unremitted_close, closing_distribution_capacity=capacity_close,
        funding_shortfall=shortfall, funding_status='SHORTFALL' if shortfall else 'FUNDED',
        cash_policy=dict(policy))
    row['clean_surplus_residual'] = book_close - state['book'] - profit + distribution
    row['capital_identity_residual'] = book_close - operating_close - cash_close - unremitted_close
    next_state = dict(book=book_close, cash=cash_close, unremitted=unremitted_close,
        capacity=capacity_close, operating=operating_close,
        productive=state['productive'] + operating_addition)
    return row, next_state


def compile_joint_capital_cash_path(*, start_book, historical, drivers, terminal_policy):
    """Ten sequential years and one separately constrained terminal step.

    Exact keys are the exported *_FIELDS sets. historical scope=SCOPE,
    currency=CNY. drivers.years is a list ordered year=1..10. All other numeric
    inputs are plain Decimal strings. Terminal positive profit_scale applies to
    year-ten total profit; a nonempty rationale is mandatory. Three terminal
    cash amounts must be supplied, including explicit zero if none recurs.
    Signed WC permits a declared release. No annual commitment carries over.
    """
    _keys(historical, HISTORICAL_FIELDS)
    _keys(drivers, DRIVER_FIELDS)
    economic_terminal = {'terminal_mechanism', 'terminal_start_year',
        'first_distribution_timing', 'legacy_profit_dynamics',
        'commitment_occurrences', 'restricted_cash_release_cny',
        'restricted_cash_release_year', 'convergence_tolerance_cny',
        'max_tail_years'}
    if (type(terminal_policy) is not dict
            or set(terminal_policy) != TERMINAL_FIELDS | economic_terminal):
        raise ValueError('Exact joint cash terminal fields required')
    if (terminal_policy['terminal_mechanism'] != 'recursive_capital_use_and_owner_distribution_v2'
            or terminal_policy['terminal_start_year'] != 11
            or terminal_policy['first_distribution_timing'] != 'end_of_terminal_year_1'
            or terminal_policy['legacy_profit_dynamics'] != 'constant_after_profit_scale_transition'):
        raise ValueError('Explicit supported terminal economic mechanism required')
    if historical['scope'] != SCOPE or historical['currency'] != 'CNY':
        raise ValueError('Explicit owner-equivalent CNY scope required')
    if type(terminal_policy['rationale']) is not str or not terminal_policy['rationale'].strip():
        raise ValueError('Explicit terminal continuation rationale required')
    if type(drivers['years']) is not list or len(drivers['years']) != 10:
        raise ValueError('Exactly ten ordered annual rows required')
    with localcontext() as context:
        context.prec = 48
        h = {k: _number(v) for k, v in historical.items() if k not in ('scope', 'currency')}
        book = _number(start_book)
        if (book <= 0 or h['revenue'] <= 0 or h['pre_tax_profit'] <= 0
                or not 0 <= h['tax'] < h['pre_tax_profit']
                or h['parent_profit'] <= 0 or h['parent_profit'] - h['nonrecurring'] <= 0
                or any(h[k] < 0 for k in ('cost', *_EXPENSES, 'da', 'opening_cash',
                    'opening_distribution_capacity', 'cash_floor'))
                or h['opening_cash'] > book):
            raise ValueError('Unsupported historical signs or opening capital')
        historical_post_tax_profit = h['pre_tax_profit'] - h['tax']
        historical_non_parent_profit = historical_post_tax_profit - h['parent_profit']
        # Signed non-parent losses can make attribution exceed one. This is an
        # earnings bridge from caller-bound history, never an ownership fraction.
        parent_attribution_ratio = h['parent_profit'] / historical_post_tax_profit
        allocation = _rate(drivers['operating_allocation'])
        op_return = _rate(drivers['new_operating_return'])
        liquidity_return = _rate(drivers['new_liquidity_return'])
        annual = []
        for year, raw in enumerate(drivers['years'], 1):
            _keys(raw, ANNUAL_FIELDS)
            if type(raw['year']) is not int or raw['year'] != year:
                raise ValueError('Annual rows must be ordered years 1 through 10')
            growth = _number(raw['revenue_growth'])
            if growth <= -1:
                raise ValueError('Revenue growth must exceed -1')
            annual.append((growth, _rate(raw['cost_ratio']), _cash_policy(raw)))
        terminal_cash = _cash_policy(terminal_policy)
        occurrences = terminal_policy['commitment_occurrences']
        if occurrences is not None and (type(occurrences) is not int or occurrences < 0):
            raise ValueError('commitment_occurrences must be a nonnegative integer or null')
        release = _number(terminal_policy['restricted_cash_release_cny'])
        release_year = terminal_policy['restricted_cash_release_year']
        if release < 0 or (release and (type(release_year) is not int or release_year < 1)):
            raise ValueError('Restricted release requires a positive terminal year')
        if not release and release_year is not None:
            raise ValueError('Restricted release year requires a positive release')
        tolerance = _number(terminal_policy['convergence_tolerance_cny'])
        max_tail_years = terminal_policy['max_tail_years']
        if tolerance <= 0 or type(max_tail_years) is not int or max_tail_years < 1:
            raise ValueError('Positive convergence tolerance and max_tail_years required')
        scale = _number(terminal_policy['profit_scale'])
        if scale <= 0:
            raise ValueError('Terminal profit scale must be positive')
        tax_rate = h['tax'] / h['pre_tax_profit']
        expense_ratios = {k: h[k] / h['revenue'] for k in _EXPENSES}
        other_pbt = h['pre_tax_profit'] - h['revenue'] + h['cost'] + sum(h[k] for k in _EXPENSES)
        state = dict(book=book, cash=h['opening_cash'], unremitted=_ZERO,
            capacity=h['opening_distribution_capacity'], operating=book-h['opening_cash'],
            productive=_ZERO)
        revenue, rows = h['revenue'], []
        for year, (growth, cost_ratio, policy) in enumerate(annual, 1):
            revenue *= 1 + growth
            cost = revenue * cost_ratio
            expenses = {k: revenue * ratio for k, ratio in expense_ratios.items()}
            pbt = revenue - cost - sum(expenses.values()) + other_pbt
            tax = pbt * tax_rate
            legacy = (pbt - tax) * parent_attribution_ratio - h['nonrecurring']
            op_profit = state['productive'] * op_return
            liquidity_profit = (state['cash'] - h['opening_cash']) * liquidity_return
            profit = legacy + op_profit + liquidity_profit
            row, state = _step(year=year, profit=profit, state=state, policy=policy,
                allocation=allocation, floor=h['cash_floor'])
            row.update(revenue=revenue, cost=cost, expenses=expenses,
                pre_tax_profit=pbt, tax=tax, legacy_parent_profit=legacy,
                new_operating_profit=op_profit, new_liquidity_profit=liquidity_profit,
                historical_da_anchor=h['da'], other_pre_tax_balance=other_pbt,
                historical_non_parent_profit=historical_non_parent_profit,
                parent_attribution_ratio=parent_attribution_ratio)
            rows.append(row)
        terminal_contract = TerminalEconomicContract(opening_book=state['book'],
            opening_cash=state['cash'], opening_unremitted=state['unremitted'],
            opening_distribution_capacity=state['capacity'],
            opening_operating_capital=state['operating'],
            opening_productive_capital=state['productive'],
            opening_cash_reference=h['opening_cash'], cash_floor=h['cash_floor'],
            legacy_profit=rows[-1]['legacy_parent_profit'] * scale,
            operating_allocation=allocation, productive_marginal_return=op_return,
            liquidity_return=liquidity_return,
            policy=tuple((key, terminal_cash[key]) for key in sorted(terminal_cash)),
            commitment_occurrences=occurrences,
            restricted_cash_release_cny=release,
            restricted_cash_release_year=release_year,
            convergence_tolerance_cny=tolerance, max_tail_years=max_tail_years,
            rationale=terminal_policy['rationale'])
        terminal, _ = _advance_terminal(terminal_contract, state, 1)
        terminal.update(historical_non_parent_profit=historical_non_parent_profit,
            parent_attribution_ratio=parent_attribution_ratio)
        terminal_roe = terminal['forecast_roe']
        terminal_retention = terminal['retention']
        return dict(version='joint-capital-cash-path-v4', action='no_order', scope=SCOPE,
            currency='CNY', status='CONDITIONAL_RESEARCH_NOT_APPROVED', rows=rows,
            terminal_mechanism=terminal_policy['terminal_mechanism'],
            terminal_start_year=terminal_policy['terminal_start_year'],
            first_distribution_timing=terminal_policy['first_distribution_timing'],
            legacy_profit_dynamics=terminal_policy['legacy_profit_dynamics'],
            historical_non_parent_profit=historical_non_parent_profit,
            parent_attribution_ratio=parent_attribution_ratio,
            forecast_roe=tuple(row['forecast_roe'] for row in rows),
            forecast_retentions=tuple(row['retention'] for row in rows), terminal=terminal,
            terminal_roe=terminal_roe, terminal_retention=terminal_retention,
            terminal_growth=terminal_retention * terminal_roe,
            terminal_growth_status='NON_AUTHORITATIVE_ACCOUNTING_DIAGNOSTIC',
            terminal_economic_contract=terminal_contract,
            terminal_profit=terminal['profit'], terminal_distribution=terminal['distribution'],
            terminal_book=state['book'], terminal_policy=dict(terminal_policy),
            funding_status='SHORTFALL' if any(row['funding_shortfall'] for row in [*rows, terminal]) else 'FUNDED',
            limitations=(
                'Earnings, access, reserves and returns are hypotheses, not legal cash facts.',
                'Historical non-parent profit is signed; negative values permit parent attribution above one.',
                'Parent attribution holds caller source-bound historical earnings ratios constant; it is not an ordinary-share ownership percentage or proven future NCI.',
                'Net maintenance is after expensed DA; no DA cash add-back is made.',
                'Mandatory assets earn no incremental return; productive capital is separate.',
                'Unremitted balances have no automatic release or yield.',
                'Terminal needs recur explicitly; annual commitments do not carry over.',
                'Retention times book ROE is diagnostic only, not terminal growth authority.',
                'Terminal value requires the explicit recursive economic contract.'))
