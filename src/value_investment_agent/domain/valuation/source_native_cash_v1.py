"""Replay a disclosed conditional cash ledger into RI inputs, never price it.

This bounded mechanism is temporary first-year remittance delay released in year
two. Every cash/project/funding item is required. Inputs remain research
assumptions; successful arithmetic is not accounting, economic or G3 approval.
"""
from decimal import Decimal, InvalidOperation, localcontext


def _number(value):
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError('Native cash values require explicit decimal numbers')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Native cash values require valid decimal numbers') from error
    if not result.is_finite():
        raise ValueError('Native cash values must be finite')
    return result


def replay_timing_delay_inputs(*, plan, scenarios, opening_book, history):
    """Recompute cash/equity transitions; do not consume sealed expected prices."""
    if set(scenarios) != {'bear', 'base', 'bull'} or plan['horizon'] != 5:
        raise ValueError('Native cash requires exactly three five-year scenarios')
    if history.get('unit') != 'CNY' or history.get('scope') != 'standalone parent, NOT consolidated free cash':
        raise ValueError('Native cash historical unit/ownership scope mismatch')
    result = {}
    annual_bases = [row for period, row in history['periods'].items()
                    if len(period) == 6 and period.startswith('FY') and period[2:].isdigit()]
    if len(annual_bases) != 1:
        raise ValueError('Native cash needs one explicit annual cash-spending basis, not a guessed latest period')
    with localcontext() as context:
        context.prec = 48
        q = _number(plan['incremental_parent_cash_yield'])
        retention = _number(plan['explicit_retention'])
        held_fraction = _number(plan['TIMING_DELAY']['withheld_fraction'])
        if (plan['TIMING_DELAY']['withheld_years'] != [1]
                or any(type(year) is not int for year in plan['TIMING_DELAY']['withheld_years'])
                or not 0 <= retention <= 1
                or not 0 <= held_fraction <= 1 or q < 0):
            raise ValueError('Unsupported native timing/retention assumptions')
        for name, case in scenarios.items():
            if case['branch'] != 'TIMING_DELAY' or case['blockers']:
                raise ValueError('Native cash supports only unblocked TIMING_DELAY research')
            rows = case['annual_rows']
            if len(rows) != 5:
                raise ValueError('Native cash ledger must contain five complete years')
            book = _number(opening_book)
            cash0 = cash = _number(history['ttm']['cash_end'])
            delayed = Decimal(0)
            parent_book = _number(history['ttm']['parent_equity_end'])
            parent_re = _number(history['ttm']['parent_retained_profit_end'])
            floor = _number(case['cash_floor'])
            project = _number(case['project_budget'])/5
            call = _number(plan['known_uncalled_fund_commitment']['amount_cny'])
            if (floor != _number(annual_bases[0]['operating_outflows'])/2
                    or call != _number(history['known_uncalled_fund_commitment']['amount_cny'])
                    or min(floor, project, call) < 0):
                raise ValueError('Native cash floor/commitment policy or history mismatch')
            paid_fund = Decimal(0)
            roes = []
            for year, row in enumerate(rows, 1):
                if type(row['year']) is not int or row['year'] != year:
                    raise ValueError('Native cash ledger years must be consecutive')
                legacy = _number(row['legacy_profit_before_new_cash_cost'])
                income = q*(cash-cash0)
                profit = legacy+income
                withheld = held_fraction*profit if year == 1 else Decimal(0)
                released = delayed if year == 2 else Decimal(0)
                funds = profit-withheld+released
                appropriation = Decimal('.10')*max(Decimal(0), funds)
                planned = (1-retention)*profit
                fund_call = call if year == 1 else Decimal(0)
                cash_capacity = max(Decimal(0), cash+funds-project-fund_call-floor)
                re_capacity = max(Decimal(0), parent_re+funds-appropriation)
                dividend = min(planned, cash_capacity, re_capacity)
                if profit <= 0 or book <= 0 or dividend != planned:
                    raise ValueError('Native cash needs variable retention or unsupported economics')
                paid_fund += fund_call
                calculated = dict(opening_book=book, opening_parent_cash=cash, opening_delayed_asset=delayed,
                    incremental_parent_cash_income=income, permanent_after_tax_cash_expense=Decimal(0),
                    profit=profit, newly_withheld=withheld, released=released, parent_net_funds=funds,
                    assumed_parent_standalone_profit=funds, statutory_appropriation=appropriation,
                    dividend_planned=planned, dividend_paid=dividend, actual_retention=(profit-dividend)/profit,
                    cash_capacity=cash_capacity, retained_profit_capacity=re_capacity,
                    project_cash=project, fund_capital_call=fund_call, fund_asset_at_cost=paid_fund,
                    cash_close=cash+funds-project-fund_call-dividend, delayed_close=delayed+withheld-released,
                    roe=profit/book, book_close=book+profit-dividend,
                    parent_equity_close=parent_book+funds-dividend,
                    parent_retained_profit_close=parent_re+funds-appropriation-dividend,
                    cash_bridge_residual=Decimal(0))
                for field, value in calculated.items():
                    if abs(_number(row[field])-value) > Decimal('1E-35'):
                        raise ValueError('Native cash ledger mismatch: '+name+'.'+field)
                if calculated['cash_close'] < floor or calculated['parent_retained_profit_close'] < 0:
                    raise ValueError('Native cash floor or retained profit failed')
                roes.append(calculated['roe'])
                book, cash, delayed, parent_book, parent_re = (calculated[field] for field in (
                    'book_close', 'cash_close', 'delayed_close', 'parent_equity_close', 'parent_retained_profit_close'))
            terminal_profit = legacy+q*(cash-cash0)
            terminal_states = dict(terminal_profit=terminal_profit, terminal_cash=cash,
                terminal_delayed_asset=delayed, terminal_book=book, parent_retained_profit_end=parent_re,
                terminal_incremental_cash_income=q*(cash-cash0), terminal_roe=terminal_profit/book)
            if any(abs(_number(case[field])-value) > Decimal('1E-35')
                   for field, value in terminal_states.items()):
                raise ValueError('Native cash terminal states differ from replayed ledger')
            if (delayed != 0 or _number(case['terminal_appropriation']) != 0
                    or _number(case['terminal_growth']) != 0 or _number(case['terminal_retention']) != 0
                    or _number(case['terminal_funding_gap']) != 0
                    or abs(_number(case['terminal_parent_funds'])-terminal_profit) > Decimal('1E-35')
                    or abs(_number(case['terminal_assumed_dividend'])-terminal_profit) > Decimal('1E-35')):
                raise ValueError('Native cash terminal funding is unsupported')
            result[name] = dict(cost_of_equity=str(_number(plan['ke'])), forecast_roes=list(map(str, roes)),
                retention=str(retention), terminal_roe=str(terminal_profit/book), terminal_growth='0')
    return result
