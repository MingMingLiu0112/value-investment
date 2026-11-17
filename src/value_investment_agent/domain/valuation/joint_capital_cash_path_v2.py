"""Pure ten-year owner-equivalent cash hypotheses; no I/O or approval.

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
commitments. Its derived growth is conditional RI continuation; the caller must
reject growth >= required return and any funding shortfall.
"""
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
    _keys(terminal_policy, TERMINAL_FIELDS)
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
        terminal, _ = _step(year=11, profit=rows[-1]['profit'] * scale,
            state=state, policy=terminal_cash, allocation=allocation, floor=h['cash_floor'])
        terminal.update(historical_non_parent_profit=historical_non_parent_profit,
            parent_attribution_ratio=parent_attribution_ratio)
        terminal_roe = terminal['forecast_roe']
        terminal_retention = terminal['retention']
        return dict(version='joint-capital-cash-path-v2', action='no_order', scope=SCOPE,
            currency='CNY', status='CONDITIONAL_RESEARCH_NOT_APPROVED', rows=rows,
            historical_non_parent_profit=historical_non_parent_profit,
            parent_attribution_ratio=parent_attribution_ratio,
            forecast_roe=tuple(row['forecast_roe'] for row in rows),
            forecast_retentions=tuple(row['retention'] for row in rows), terminal=terminal,
            terminal_roe=terminal_roe, terminal_retention=terminal_retention,
            terminal_growth=terminal_retention * terminal_roe,
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
                'Caller must reject funding shortfalls and growth >= required return.'))
