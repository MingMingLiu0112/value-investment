"""Book-balance funding stresses; never a cash forecast or dividend approval."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext


CURRENT_COMPONENTS = (
    'short_term_borrowings', 'trade_payables', 'advance_receipts',
    'contract_liabilities', 'employee_payables', 'tax_payables',
    'other_payables_including_dividend', 'current_noncurrent_liabilities',
    'other_current_liabilities',
)
DEBT_COMPONENTS = ('short_term_borrowings', 'current_noncurrent_liabilities')
REQUIRED_BALANCES = (*CURRENT_COMPONENTS, 'current_liabilities_total',
                     'dividend_payable', 'cash_equivalents', 'noncurrent_borrowings',
                     'retained_profit')


def _decimal(value, *, signed=False):
    if type(value) not in (str, int, Decimal):
        raise ValueError('Explicit decimal required')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    if not result.is_finite() or (not signed and result < 0):
        raise ValueError('Finite nonnegative amount required')
    return result


def evaluate_parent_obligation_pressure(*, snapshot, scenario):
    """Reserve book amounts under explicit no-flow assumptions, not due-date facts.

    A balance-sheet liability may settle in goods/services, internally or after
    refinancing. Reserving its full book value is a *stress assumption*. Interest
    already in the borrowed balance is not added again. No arbitrary blank row
    is interpreted as zero: the adapter supplies a fully reconciled component
    set. Legal distributable profit and future funding are not inferred.
    """
    if snapshot.get('scope') != 'issuer_parent_standalone' or snapshot.get('unit') != 'CNY':
        raise ValueError('Standalone parent CNY snapshot required')
    as_of = snapshot.get('as_of')
    if not isinstance(as_of, str) or date.fromisoformat(as_of).isoformat() != as_of:
        raise ValueError('Exact snapshot date required')
    if not isinstance(snapshot.get('symbol'), str) or len(snapshot['symbol']) != 6 or not snapshot['symbol'].isdigit():
        raise ValueError('Explicit issuer required')
    if set(snapshot.get('balances', {})) != set(REQUIRED_BALANCES):
        raise ValueError('Complete explicit balance set required')
    expected = {'scenario_id', 'reserve_other_current', 'reserve_noncurrent_borrowings',
                'cash_floor_cny', 'floor_includes_debt', 'future_investment_reserve_cny',
                'hypothetical_additional_distribution_cny'}
    if set(scenario) != expected or not isinstance(scenario['scenario_id'], str) or not scenario['scenario_id']:
        raise ValueError('Explicit complete scenario required')
    for key in ('reserve_other_current', 'reserve_noncurrent_borrowings', 'floor_includes_debt'):
        if type(scenario[key]) is not bool:
            raise ValueError('Explicit boolean required')
    with localcontext() as ctx:
        ctx.prec = 48
        b = {key: _decimal(value, signed=key == 'retained_profit')
             for key, value in snapshot['balances'].items()}
        if sum(b[key] for key in CURRENT_COMPONENTS) != b['current_liabilities_total']:
            raise ValueError('Current liabilities do not reconcile; no blank-to-zero inference')
        if b['dividend_payable'] > b['other_payables_including_dividend']:
            raise ValueError('Dividend must be contained in other payables')
        debt = sum(b[key] for key in DEBT_COMPONENTS)
        # Dividend is reserved once; other-payables residual is not a second dividend.
        other = b['current_liabilities_total'] - b['dividend_payable'] - debt
        selected_other = other if scenario['reserve_other_current'] else Decimal(0)
        noncurrent = b['noncurrent_borrowings'] if scenario['reserve_noncurrent_borrowings'] else Decimal(0)
        floor = _decimal(scenario['cash_floor_cny'])
        investment = _decimal(scenario['future_investment_reserve_cny'])
        target = _decimal(scenario['hypothetical_additional_distribution_cny'])
        # Only the explicitly selected debt reservation can overlap the floor.
        overlap = min(floor, debt + noncurrent) if scenario['floor_includes_debt'] else Decimal(0)
        incremental_floor = floor - overlap
        after_dividend = b['cash_equivalents'] - b['dividend_payable']
        residual = after_dividend - debt - selected_other - noncurrent - incremental_floor - investment
        numeric = dict(cash_after_declared_dividend_cny=after_dividend,
            debt_book_reserve_cny=debt,
            other_payables_ex_dividend_cny=b['other_payables_including_dividend'] - b['dividend_payable'],
            other_current_book_reserve_cny=selected_other,
            noncurrent_borrowings_reserve_cny=noncurrent,
            cash_floor_cny=floor, floor_debt_overlap_cny=overlap,
            incremental_floor_cny=incremental_floor,
            future_investment_reserve_cny=investment,
            conditional_cash_residual_cny=residual,
            hypothetical_additional_distribution_cny=target,
            conditional_target_gap_cny=max(target - residual, Decimal(0)))
    return dict(schema_version='parent-obligation-pressure-v2',
        status='CONDITIONAL_BOOK_BALANCE_STRESS_NOT_CAPACITY',
        symbol=snapshot['symbol'], as_of=as_of, scope=snapshot['scope'], unit='CNY',
        scenario_id=scenario['scenario_id'], assumptions=dict(scenario),
        floor_semantics=('COMBINED_DEBT_AND_CASH_BUFFER_ALTERNATIVE'
            if scenario['floor_includes_debt'] else 'MINIMUM_CASH_REMAINING_AFTER_SELECTED_USES'),
        original_minimum_cash_floor_semantics_preserved=not scenario['floor_includes_debt'],
        **{key: str(value) for key, value in numeric.items()},
        cashflow_assumption='NO_INTERVENING_INFLOWS_OUTFLOWS_OR_REFINANCING',
        reserve_treatment='BOOK_VALUE_RESERVATION_NOT_PREDICTED_CASH_SETTLEMENT',
        legal_retained_profit_cny=str(b['retained_profit']),
        retained_profit_is_legal_capacity=False, current_parent_cash_cny=None,
        current_distribution_capacity_cny=None, actual_funding_shortfall_cny=None,
        exact_due_dates_proven=False, current_capacity_proven=False,
        formal_eligibility=False, financial_admission=False, economic_approval=False,
        price_admitted=False, strategy_admitted=False, action_admitted=False,
        action='no_order')
