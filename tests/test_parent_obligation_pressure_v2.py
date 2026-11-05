from copy import deepcopy
from decimal import Decimal

import pytest

from value_investment_agent.domain.research.parent_obligation_pressure_v2 import (
    evaluate_parent_obligation_pressure,
)


def snapshot():
    # Synthetic values exercise containment/reconciliation, not issuer evidence.
    return dict(symbol='123456', as_of='2026-06-30', scope='issuer_parent_standalone', unit='CNY',
        balances=dict(short_term_borrowings='30', current_noncurrent_liabilities='15',
            trade_payables='2', advance_receipts='1', contract_liabilities='3',
            employee_payables='4', tax_payables='1', other_current_liabilities='1',
            other_payables_including_dividend='120', current_liabilities_total='177',
            dividend_payable='65', cash_equivalents='235', noncurrent_borrowings='12',
            retained_profit='232'))


def scenario(**changes):
    value = dict(scenario_id='SYNTHETIC', reserve_other_current=False,
        reserve_noncurrent_borrowings=False, cash_floor_cny='60', floor_includes_debt=False,
        future_investment_reserve_cny='0', hypothetical_additional_distribution_cny='85')
    value.update(changes)
    return value


def run(s=None, **changes):
    return evaluate_parent_obligation_pressure(snapshot=s or snapshot(), scenario=scenario(**changes))


def test_short_and_current_debt_reserved_separately_once():
    r = run()
    assert r['debt_book_reserve_cny'] == '45'
    assert r['cash_after_declared_dividend_cny'] == '170'
    assert r['conditional_cash_residual_cny'] == '65'
    assert r['conditional_target_gap_cny'] == '20'


def test_other_payables_containment_and_floor_overlap_are_not_double_deducted():
    r = run(reserve_other_current=True)
    assert r['other_payables_ex_dividend_cny'] == '55'
    assert r['other_current_book_reserve_cny'] == '67'
    assert r['conditional_cash_residual_cny'] == '-2'
    inclusive = run(reserve_other_current=True, floor_includes_debt=True)
    assert inclusive['floor_debt_overlap_cny'] == '45'
    assert inclusive['incremental_floor_cny'] == '15'
    assert inclusive['conditional_cash_residual_cny'] == '43'
    assert inclusive['original_minimum_cash_floor_semantics_preserved'] is False
    assert r['original_minimum_cash_floor_semantics_preserved'] is True


def test_floor_overlap_cannot_reserve_less_than_selected_debt():
    r = run(cash_floor_cny='10', floor_includes_debt=True)
    assert r['floor_debt_overlap_cny'] == '10'
    assert r['incremental_floor_cny'] == '0'
    assert r['conditional_cash_residual_cny'] == '125'


def test_noncurrent_borrowing_is_only_reserved_when_explicitly_selected():
    normal = run()
    stress = run(reserve_noncurrent_borrowings=True)
    assert normal['noncurrent_borrowings_reserve_cny'] == '0'
    assert stress['noncurrent_borrowings_reserve_cny'] == '12'
    assert Decimal(normal['conditional_cash_residual_cny']) - Decimal(stress['conditional_cash_residual_cny']) == 12


@pytest.mark.parametrize('key', ['reserve_other_current', 'reserve_noncurrent_borrowings', 'floor_includes_debt'])
@pytest.mark.parametrize('value', ['false', 1, None])
def test_flags_never_use_truthiness(key, value):
    with pytest.raises(ValueError, match='boolean'):
        run(**{key: value})


@pytest.mark.parametrize('value', [True, 1.5, None, 'NaN', 'Infinity', '-1'])
def test_reserves_require_explicit_nonnegative_finite_decimals(value):
    with pytest.raises(ValueError):
        run(future_investment_reserve_cny=value)


@pytest.mark.parametrize('changes', [dict(scope='consolidated'), dict(unit='USD'), dict(as_of='2026-6-30')])
def test_scope_unit_and_date_rejected(changes):
    s = snapshot()
    s.update(changes)
    with pytest.raises(ValueError):
        run(s)


def test_missing_or_inconsistent_balances_cannot_be_assumed_zero():
    for key in ('short_term_borrowings', 'trade_payables'):
        s = snapshot()
        del s['balances'][key]
        with pytest.raises(ValueError, match='balance set'):
            run(s)
    s = snapshot()
    s['balances']['current_liabilities_total'] = '176'
    with pytest.raises(ValueError, match='reconcile'):
        run(s)


def test_dividend_outside_other_payables_rejected():
    s = snapshot()
    s['balances']['dividend_payable'] = '121'
    with pytest.raises(ValueError, match='contained'):
        run(s)


def test_zero_gap_negative_retained_profit_and_no_order_do_not_grant_capacity():
    s = snapshot()
    s['balances']['retained_profit'] = '-1'
    before = deepcopy(s)
    r = run(s, floor_includes_debt=True)
    assert r['conditional_target_gap_cny'] == '0'
    assert r['current_distribution_capacity_cny'] is None
    assert r['actual_funding_shortfall_cny'] is None
    assert r['retained_profit_is_legal_capacity'] is False
    assert r['formal_eligibility'] is False and r['current_capacity_proven'] is False
    assert r['action'] == 'no_order' and s == before


def test_explicit_future_investment_reduces_only_the_conditional_residual():
    r = run(future_investment_reserve_cny='5')
    assert r['conditional_cash_residual_cny'] == '60'
    assert r['current_parent_cash_cny'] is None


def test_application_publishes_alternatives_not_an_adopted_best_case(monkeypatch):
    from datetime import datetime, timezone
    from value_investment_agent.application.research import parent_obligation_review_v2 as app
    trusted = snapshot()
    monkeypatch.setattr(app, 'load_parent_obligation_snapshot', lambda **kw: trusted)
    monkeypatch.setattr(app, 'load_frozen_cash_floor_assumption', lambda **kw: dict(value='60'))
    before = deepcopy(trusted)
    kwargs = dict(root='unused', native_path='unused', floor_assumption_path='unused',
        cutoff=datetime(2026, 11, 1, tzinfo=timezone.utc),
        hypothetical_additional_distribution_cny='85', future_investment_reserve_cny='0')
    r = app.review_parent_obligations_v2(**kwargs)
    assert len(r['scenarios']) == 4
    assert len({s['scenario_id'] for s in r['scenarios']}) == 4
    assert r['illustrative_residual_span_cny']['minimum'] == '-2'
    assert r['illustrative_residual_span_cny']['maximum'] == '110'
    assert all(s['current_capacity_proven'] is False for s in r['scenarios'])
    assert r['hypothetical_distribution_is_declared_liability'] is False
    assert r['annual_policy_fulfillment_assessed'] is False
    assert r['economic_approval'] is False and r['action'] == 'no_order'
    assert r['review_fingerprint'] == app.review_parent_obligations_v2(**kwargs)['review_fingerprint']
    assert trusted == before
