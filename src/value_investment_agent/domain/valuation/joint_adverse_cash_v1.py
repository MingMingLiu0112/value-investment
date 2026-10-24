"""One five-year JS2 cash counterexample, not a forecast or a valuation.

Freeze the inherited payout and parent-profit mapping. Repeat the disclosed FY
ex-parent decline and withhold fresh funds every year, with no release. Stop at
the first infeasible planned payout: never silently cut dividends or borrow.
The caller must verify the original source closure before and after this pure
calculation. Source metadata here is attribution, not evidence authentication.
The frozen v1 replay only admits withholding in year one, full release in year
two and U=0 at terminal. It cannot represent this repeated non-release case.
Only its strict decimal parser is reused; no frozen formula or file is changed.
"""
from copy import deepcopy
from decimal import Decimal, localcontext

from .source_native_cash_v1 import _number


EX_PARENT_LABEL = "归属于上市公司股东的扣除非经常性损益的净利润"


def diagnose_joint_adverse_cash(*, annual_profit_fact, profit_anchor, plan,
                               history, opening_book, project_budget):
    """Return P/M/U/C/B/planned-D through the first cash/RE policy failure.

    P is consolidated parent profit, M assumed standalone parent funds/profit,
    U still-owned unremitted assets, C parent cash, B consolidated parent equity.
    D is an attempted 90% payout, NOT dividend paid. This is an annual budget,
    not evidence of payment-date liquidity or legally distributable profits.
    Failure rows are unfunded
    counterfactuals; later years are not manufactured. There is no terminal.
    """
    fact, plan, history = map(deepcopy, (annual_profit_fact, plan, history))
    if (fact.get('label') != EX_PARENT_LABEL
            or fact.get('periods') != ['FY2025', 'FY2024']
            or fact.get('scope') != 'CONSOLIDATED_AFTER_TAX_PARENT'
            or fact.get('unit') != 'CNY' or fact.get('currency') != 'CNY'
            or not isinstance(fact.get('values'), list) or len(fact['values']) != 2):
        raise ValueError('Diagnostic requires the exact FY ex-parent comparison row')
    if (history.get('unit') != 'CNY'
            or history.get('scope') != 'standalone parent, NOT consolidated free cash'):
        raise ValueError('Diagnostic requires standalone parent CNY history')
    annual = [row for period, row in history['periods'].items()
              if len(period) == 6 and period.startswith('FY') and period[2:].isdigit()]
    if len(annual) != 1 or 'FY2025' not in history['periods']:
        raise ValueError('Diagnostic requires one FY2025 spending basis')
    if (type(plan['horizon']) is not int or plan['horizon'] != 5
            or plan['TIMING_DELAY']['withheld_years'] != [1]
            or any(type(year) is not int for year in plan['TIMING_DELAY']['withheld_years'])):
        raise ValueError('Diagnostic requires the original five-year single-delay baseline')
    with localcontext() as context:
        context.prec = 48
        current, previous = map(_number, fact['values'])
        if not 0 < current < previous:
            raise ValueError('Diagnostic requires a positive disclosed annual earnings decline')
        ratio = current / previous
        anchor, book = _number(profit_anchor), _number(opening_book)
        cash0 = cash = _number(history['ttm']['cash_end'])
        parent_book = _number(history['ttm']['parent_equity_end'])
        retained = _number(history['ttm']['parent_retained_profit_end'])
        floor = _number(annual[0]['operating_outflows']) / 2
        project = _number(project_budget) / 5
        call = _number(plan['known_uncalled_fund_commitment']['amount_cny'])
        if (call != _number(history['known_uncalled_fund_commitment']['amount_cny'])
                or min(floor, project, call, cash, retained) < 0
                or min(anchor, book, parent_book) <= 0 or cash < floor):
            raise ValueError('Diagnostic opening balances or inherited commitments unsupported')
        retention = _number(plan['explicit_retention'])
        held = _number(plan['TIMING_DELAY']['withheld_fraction'])
        cash_yield = _number(plan['incremental_parent_cash_yield'])
        if (retention, held, cash_yield) != (Decimal('.10'), Decimal('.10'), Decimal('.01')):
            raise ValueError('Diagnostic freezes JS2 retention, withholding and cash yield')
        delayed = Decimal(0)
        rows = []
        cash_failure = retained_failure = None
        unsupported = None
        for year in range(1, 6):
            legacy = anchor * ratio ** year
            income = cash_yield * (cash - cash0)
            profit = legacy + income
            if profit <= 0 or book <= 0:
                unsupported = 'NONPOSITIVE_PROFIT_OR_EQUITY_NO_SUPPORTED_CASH_MAPPING'
                break
            withheld, release = held * profit, Decimal(0)
            funds = profit - withheld + release
            appropriation = Decimal('.10') * max(Decimal(0), funds)
            dividend = (1 - retention) * profit
            fund_call = call if year == 1 else Decimal(0)
            cash_capacity = max(Decimal(0), cash + funds - project - fund_call - floor)
            re_capacity = max(Decimal(0), retained + funds - appropriation)
            cash_close = cash + funds - project - fund_call - dividend
            re_close = retained + funds - appropriation - dividend
            delayed_close = delayed + withheld - release
            book_close = book + profit - dividend
            parent_close = parent_book + funds - dividend
            cash_failed = dividend > cash_capacity or cash_close < floor
            re_failed = dividend > re_capacity or re_close < 0
            row = dict(year=year, legacy_profit=legacy, incremental_cash_income=income,
                P=profit, M=funds, U_open=delayed, U=delayed_close,
                newly_withheld=withheld, released=release,
                C_open=cash, C=cash_close, B_open=book, B=book_close, D=dividend,
                D_scope='PLANNED_NOT_PAID_NO_AUTOMATIC_DIVIDEND_CUT',
                parent_equity_open=parent_book, parent_equity=parent_close,
                retained_profit_open=retained, retained_profit=re_close,
                statutory_appropriation=appropriation, project_cash=project,
                fund_capital_call=fund_call, cash_capacity=cash_capacity,
                retained_profit_capacity=re_capacity, cash_floor=floor,
                cash_margin=cash_close-floor, retained_profit_margin=re_close,
                cash_constraint_failed=cash_failed, retained_constraint_failed=re_failed,
                status='UNFUNDED_PLAN' if cash_failed or re_failed else 'CONDITIONAL_PLAN_FEASIBLE',
                cash_bridge_residual=cash_close-(cash+funds-project-fund_call-dividend),
                ownership_bridge_residual=(book_close-parent_close)-(book-parent_book)
                    -(delayed_close-delayed))
            rows.append(row)
            if cash_failed:
                cash_failure = year
            if re_failed:
                retained_failure = year
            cash, book, parent_book, retained, delayed = (
                cash_close, book_close, parent_close, re_close, delayed_close)
            if cash_failed or re_failed:
                break
        failed = cash_failure is not None or retained_failure is not None
        return dict(method='FY_DECLINE_REPEATED_FIVE_YEARS_FRESH_WITHHOLDING_NO_RELEASE_V1',
            scope='MECHANICAL_COUNTEREXAMPLE_NOT_FORECAST_OR_ACCOUNTING_FACT',
            source_authentication='CALLER_MUST_VERIFY_BOUND_ORIGINALS_AND_FINAL_CLOSURE',
            annual_profit_fact=fact, disclosed_annual_growth=ratio-1,
            profit_anchor=anchor, rows=rows, horizon=5,
            not_computed_years=list(range(len(rows)+1, 6)),
            first_cash_failure_year=cash_failure,
            first_retained_profit_failure_year=retained_failure,
            first_policy_failure_year=(len(rows) if failed else None),
            failure_observation_scope='ONLY_THROUGH_FIRST_POLICY_FAILURE_NO_ASSUMED_REPAIR',
            status=('UNSUPPORTED' if unsupported else
                    'INHERITED_PAYOUT_INFEASIBLE' if failed else 'FIVE_YEAR_CONDITIONAL_PLAN_FEASIBLE'),
            unsupported_reason=unsupported, outstanding_unremitted_assets=delayed,
            terminal_status='UNSUPPORTED_NO_RELEASE_NO_FULL_PAYOUT_TERMINAL',
            assumptions=dict(newly_withheld_fraction=held, release_within_horizon=False,
                explicit_retention=retention, incremental_parent_cash_yield=cash_yield,
                statutory_appropriation_fraction=Decimal('.10'),
                parent_profit_mapping='M_EQUALS_ASSUMED_STANDALONE_NET_PROFIT_NOT_HISTORICAL_IDENTITY',
                unremitted_asset_yield='ZERO_INHERITED_NONINTEREST_BEARING_SETTLEMENT_ASSUMPTION',
                cash_floor_policy='HALF_FY2025_PARENT_GROSS_OPERATING_OUTFLOWS',
                fund_call_policy='EXISTING_COMMITMENT_ALL_IN_YEAR_ONE',
                project_policy='INHERITED_BUDGET_FIVE_EQUAL_PAYMENTS',
                external_financing=False, automatic_dividend_cut=False),
            action='no_order')
