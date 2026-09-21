"""Explicit annual FCFF arithmetic; no data, assumption or strategy approval."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext


MODEL_VERSION = 'annual-fcff-explicit-bridge-research-v1'
ZERO = Decimal('0')
ONE = Decimal('1')


def number(value, name):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f'{name} must be a finite Decimal')
    return value


@dataclass(frozen=True)
class ForecastYear:
    year: int
    ebit: Decimal
    cash_tax_rate: Decimal
    depreciation: Decimal
    capex: Decimal
    working_capital_increase: Decimal
    wacc: Decimal
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Terminal:
    next_year_nopat: Decimal
    growth: Decimal
    roic: Decimal
    wacc: Decimal
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BridgeItem:
    name: str
    kind: str
    value: Decimal
    exposure_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def references(items, name):
    if not isinstance(items, tuple) or not items or any(
            not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f'{name} requires explicit nonempty references')
    if len(set(items)) != len(items):
        raise ValueError(f'{name} contains duplicates')


def value_scenario(*, forecast, terminal, bridge, operating_exposure_ids,
                   ordinary_shares, share_evidence_refs, currency, scenario_id,
                   valuation_date=None, cash_flow_dates=None, timing_evidence_refs=()):
    """Inputs are whole currency units, actual shares, and year-end cash flows.

    Evidence references identify caller-owned facts/assumptions; this pure
    calculator does NOT authenticate them or prove historical availability.
    Declared exposures must partition operations and asset/claim adjustments.
    """
    if not scenario_id or not isinstance(scenario_id, str):
        raise ValueError('scenario_id required')
    if currency not in {'CNY', 'USD', 'HKD'}:
        raise ValueError('Provide one supported currency; convert upstream')
    if not forecast or len(forecast) > 50:
        raise ValueError('Provide 1..50 annual forecast periods')
    dated = valuation_date is not None or cash_flow_dates is not None
    if dated:
        references(timing_evidence_refs, 'dated cash-flow convention')
        if not isinstance(valuation_date, date) or isinstance(valuation_date, datetime):
            raise ValueError('Provide an explicit valuation calendar date')
        if not isinstance(cash_flow_dates, tuple) or len(cash_flow_dates) != len(forecast):
            raise ValueError('Provide one cash-flow date per forecast period')
        previous = valuation_date
        for row, payment in zip(forecast, cash_flow_dates):
            if (not isinstance(payment, date) or isinstance(payment, datetime)
                    or payment <= previous or payment.year != row.year):
                raise ValueError('Cash-flow dates must increase after valuation and match forecast years')
            previous = payment
    elif timing_evidence_refs:
        raise ValueError('Timing references require explicit dates')
    references(operating_exposure_ids, 'operating exposures')
    references(share_evidence_refs, 'share basis')
    number(ordinary_shares, 'ordinary shares')
    if ordinary_shares <= ZERO or ordinary_shares != ordinary_shares.to_integral_value():
        raise ValueError('Use a positive actual ordinary-share count, not share capital')
    with localcontext() as context:
        context.prec = 40
        factor = ONE
        operations = ZERO
        years = []
        previous_year = None
        previous_payment = valuation_date
        for index, row in enumerate(forecast):
            if type(row.year) is not int or not 1900 <= row.year <= 2200:
                raise ValueError('Invalid forecast year')
            if previous_year is not None and row.year != previous_year + 1:
                raise ValueError('Forecast years must be consecutive and ordered')
            previous_year = row.year
            references(row.evidence_refs, 'annual forecast')
            for name in ('ebit', 'cash_tax_rate', 'depreciation', 'capex',
                         'working_capital_increase', 'wacc'):
                number(getattr(row, name), name)
            if not ZERO <= row.cash_tax_rate <= ONE or row.wacc <= ZERO:
                raise ValueError('Invalid tax rate or WACC')
            if row.depreciation < ZERO or row.capex < ZERO:
                raise ValueError('D&A and capex must be nonnegative magnitudes')
            # No immediate tax refund on a forecast loss; loss carryforwards
            # require a separately modelled tax schedule, not a negative tax.
            tax = max(row.ebit, ZERO) * row.cash_tax_rate
            nopat = row.ebit - tax
            reinvestment = row.capex - row.depreciation + row.working_capital_increase
            fcff = nopat - reinvestment
            interval = ONE
            if dated:
                payment = cash_flow_dates[index]
                interval = Decimal((payment - previous_payment).days) / Decimal(365)
                previous_payment = payment
            # ACT/365F is an explicit research convention with annual effective
            # rates. Stub-period cash amounts are supplied, never auto-prorated.
            factor /= (ONE + row.wacc) ** interval
            present_value = fcff * factor
            operations += present_value
            years.append({'year': row.year, 'nopat': nopat, 'reinvestment': reinvestment,
                          'ebit': row.ebit, 'cash_tax_rate': row.cash_tax_rate,
                          'depreciation': row.depreciation, 'capex': row.capex,
                          'working_capital_increase': row.working_capital_increase,
                          'wacc': row.wacc,
                          'discount_interval_years': interval,
                          'cash_flow_date': cash_flow_dates[index].isoformat() if dated else None,
                          'fcff': fcff, 'discount_factor': factor, 'present_value': present_value,
                          'evidence_refs': row.evidence_refs})
        references(terminal.evidence_refs, 'terminal assumptions')
        for name in ('next_year_nopat', 'growth', 'roic', 'wacc'):
            number(getattr(terminal, name), name)
        if not ZERO <= terminal.growth < terminal.wacc or terminal.roic <= ZERO:
            raise ValueError('Terminal requires 0 <= growth < WACC and positive ROIC')
        if terminal.growth > terminal.roic or terminal.next_year_nopat < ZERO:
            raise ValueError('This stable terminal model requires sustainable nonnegative FCFF')
        reinvestment_rate = terminal.growth / terminal.roic
        terminal_fcff = terminal.next_year_nopat * (ONE - reinvestment_rate)
        terminal_value = terminal_fcff / (terminal.wacc - terminal.growth)
        terminal_pv = terminal_value * factor
        operations += terminal_pv
        equity = operations
        seen = set(operating_exposure_ids)
        names = set()
        adjustments = []
        for item in bridge:
            if item.kind not in {'nonoperating_asset', 'financial_equity', 'debt',
                                 'minority', 'dilution', 'other_claim'}:
                raise ValueError('Unknown equity bridge kind')
            if not item.name or item.name in names:
                raise ValueError('Bridge names must be unique and nonempty')
            names.add(item.name)
            references(item.evidence_refs, 'bridge evidence')
            references(item.exposure_ids, 'bridge exposures')
            if seen.intersection(item.exposure_ids):
                raise ValueError('Double-counted operating/asset/claim exposure')
            seen.update(item.exposure_ids)
            number(item.value, item.name)
            if item.value < ZERO:
                raise ValueError('Bridge values use nonnegative magnitudes and explicit kinds')
            sign = ONE if item.kind in {'nonoperating_asset', 'financial_equity'} else -ONE
            equity += sign * item.value
            adjustments.append({'name': item.name, 'kind': item.kind, 'value': item.value,
                                'signed_value': sign * item.value, 'exposure_ids': item.exposure_ids,
                                'evidence_refs': item.evidence_refs})
        return {'model_version': MODEL_VERSION + ('-dated-v1' if dated else ''), 'scenario_id': scenario_id, 'currency': currency,
                'amount_unit': 'whole_currency', 'timing': 'explicit_dates_ACT_365F' if dated else 'annual_year_end',
                'valuation_date': valuation_date.isoformat() if dated else None,
                'timing_evidence_refs': timing_evidence_refs,
                'operating_exposure_ids': operating_exposure_ids, 'annual_cash_flows': years,
                'terminal_reinvestment_rate': reinvestment_rate,
                'terminal_inputs': {'next_year_nopat': terminal.next_year_nopat,
                                    'growth': terminal.growth, 'roic': terminal.roic,
                                    'wacc': terminal.wacc},
                'terminal_fcff': terminal_fcff, 'terminal_value_at_final_year': terminal_value,
                'terminal_present_value': terminal_pv, 'operating_value': operations,
                'bridge': adjustments, 'ordinary_equity_value': equity,
                'ordinary_shares': ordinary_shares, 'per_share_value': equity / ordinary_shares,
                'share_evidence_refs': share_evidence_refs,
                'terminal_evidence_refs': terminal.evidence_refs,
                'negative_equity_model_result': equity < ZERO,
                'evidence_authenticated': False, 'assumptions_validated': False,
                'strategy_approved': False, 'status': 'research_arithmetic_only'}
