"""Economic diagnostics distinguish repeatable arithmetic from admission."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path

import pytest

from test_pending_candidate_supplement import registered
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research import value_economic_assessment as economic


NOW = datetime.now(timezone.utc) + timedelta(days=1)


def test_verified_scenario_cash_and_excess_returns_are_computed_without_admission(registered):
    root, symbol, _, _ = registered
    before = {p: sha256_file(p) for p in root.rglob('*') if p.is_file()}
    result = economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)
    assert result['action'] == 'no_order'
    assert result['primary_valuation_usable'] is result['approval_changed'] is False
    assert result['action_admitted'] is result['strategy_admitted'] is False
    assert len(result['scenarios']) == 3
    for row in result['scenarios']:
        assert Decimal(row['first_year_profit_cny']) > 0
        assert Decimal(row['first_year_dividend_assumption_cny']) > 0
        assert abs(Decimal(row['dividend_ri_reconciliation_cny'])) < Decimal('.01')
        assert row['explicit_years'] >= row['years_above_equity_cost']
        assert row['diagnostic_basis'].startswith('UNDATED_BOOK')
    from value_investment_agent.application.research.value_research_analysis import load_current_value_research_analysis
    analysis = load_current_value_research_analysis(root=root, symbol=symbol, now=NOW)
    base = analysis['scenarios'][1]['inputs']
    with localcontext() as context:
        context.prec = 48
        expected = Decimal(analysis['consumed_operating_inputs']['start_book_equity']) * Decimal(base['forecast_roes'][0])
        assert Decimal(result['scenarios'][1]['first_year_profit_cny']) == expected
    assert result['reverse_expectations']['market_implied_result'] is None
    assert len(result['next_verifications']) == 5
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    later = economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW + timedelta(minutes=1))
    assert result['assessed_at'] != later['assessed_at']
    assert result['assessment_sha256'] == later['assessment_sha256']
    assert before == {p: sha256_file(p) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('name', ['package.json', 'workbench.json', 'candidate.json', 'consumed-review.json', 'original.md'])
def test_source_tamper_rejected(registered, name):
    root, symbol, candidate, _ = registered
    path = root / 'runtime/original.md' if name == 'original.md' else candidate.parent / name
    path.write_bytes(path.read_bytes() + b'corrupt')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)


def test_future_candidate_rejected(registered):
    root, symbol, candidate, _ = registered
    cutoff = datetime.fromisoformat(json.loads(candidate.read_bytes())['generated_at']) - timedelta(seconds=1)
    with pytest.raises(ValueError):
        economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=cutoff)


def test_other_symbol_does_not_consume_candidate(registered):
    root, _, _, _ = registered
    assert economic.load_current_value_economic_assessment(root=root, symbol='600519', now=NOW) is None


def test_mixed_company_payload_rejected(registered, monkeypatch):
    root, symbol, _, _ = registered
    original = economic.load_current_value_research_analysis
    def mixed(**kwargs):
        data = original(**kwargs)
        data['symbol'] = '000333'
        return data
    monkeypatch.setattr(economic, 'load_current_value_research_analysis', mixed)
    with pytest.raises(ValueError, match='identity'):
        economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)


def test_future_source_rejected_even_when_outer_candidate_is_current(registered, monkeypatch):
    root, symbol, _, _ = registered
    original = economic.load_current_value_research_analysis
    def future(**kwargs):
        data = original(**kwargs)
        data['source_catalog'][0]['source_available_at'] = (NOW + timedelta(days=1)).isoformat()
        return data
    monkeypatch.setattr(economic, 'load_current_value_research_analysis', future)
    with pytest.raises(ValueError, match='cutoff'):
        economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)


@pytest.mark.parametrize('fault', [None, 'hash', 'company', 'unit', 'arithmetic', 'future', 'scope', 'period'])
def test_historical_cash_bridge_recalculation_and_rejection(fault):
    catalog = {'official': dict(sha256='a' * 64)}
    facts = [dict(id=name, source_id='official', source_binding=dict(id='official',
        sha256='a' * 64, available_at_conservative=(NOW - timedelta(days=1)).isoformat()),
        unit='CNY', currency='CNY', columns=[dict(period='FY2025', value=value)],
        physical_page=10, evidence_excerpt=name, statement_scope='listed_parent_only')
        for name, value in [('cfo', '100'), ('investment', '20'), ('capex', '30')]]
    review = dict(symbol='600887', facts=facts, calculations={
        'calendar2025_parent_partial_cash_proxy': dict(input_fact_ids=['cfo','investment','capex'],
            input_column_indices=[0,0,0], value='90', formula='parent_CFO+investment_income_cash-gross_capex',
            scope='partial_cash_proxy_not_distributable_cash')})
    if fault == 'hash':
        facts[0]['source_binding']['sha256'] = 'b' * 64
    elif fault == 'company':
        review['symbol'] = '600519'
    elif fault == 'unit':
        facts[0]['unit'] = 'CNY_million'
    elif fault == 'arithmetic':
        review['calculations']['calendar2025_parent_partial_cash_proxy']['value'] = '120'
    elif fault == 'future':
        facts[0]['source_binding']['available_at_conservative'] = (NOW + timedelta(days=1)).isoformat()
    elif fault == 'scope':
        facts[0]['statement_scope'] = 'consolidated'
    elif fault == 'period':
        facts[0]['columns'][0]['period'] = 'H12026'
    if fault:
        with pytest.raises(ValueError):
            economic._review_calculations(review, catalog, '600887', NOW)
    else:
        row, = economic._review_calculations(review, catalog, '600887', NOW)
        assert row['recomputed_value'] == '90'
        assert [item['coefficient'] for item in row['evidence']] == [1, 1, -1]
        assert row['scope'] == 'partial_cash_proxy_not_distributable_cash'


def test_source_drift_during_computation_rejected(registered, monkeypatch):
    root, symbol, _, _ = registered
    original = economic.scenario_value
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        (root / 'runtime/original.md').write_bytes(b'drift')
        return value
    monkeypatch.setattr(economic, 'scenario_value', changed)
    with pytest.raises(ValueError, match='hash mismatch'):
        economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)


@pytest.mark.parametrize('symbol', ['600519', '600887'])
def test_real_source_bound_readonly_replay(symbol):
    location = os.environ.get('VALUE_ECONOMIC_REPLAY_ROOT')
    if not location:
        pytest.skip('Optional read-only real source tree was not supplied')
    root = Path(location)
    result = economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)
    assert result is not None
    before = {b['path']: sha256_file(root / b['path']) for b in result['source_bindings']}
    replay = economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)
    assert result == replay
    assert before == {name: sha256_file(root / name) for name in before}
    assert result['primary_valuation_usable'] is False
    assert result['earnings']['normalization_status'] == 'NOT_ESTABLISHED'
    if symbol == '600519':
        assert result['earnings']['historical_bridge']['computed_ttm_cny'] == '81367067677.44'
        assert result['model_applicability']['assessment'] == 'CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION'
    else:
        assert result['model_applicability']['assessment'] == 'STRESS_ONLY'
        assert result['historical_cash_observations']
        assert all(row['explicit_years'] == 4 for row in result['scenarios'])
        assert result['earnings']['historical_bridge']['computed_ttm_cny'] == '9647734710.01'
        cash, = result['cash_return_diagnostics']
        assert cash['difference_cny'] == '800308192.72'
        assert Decimal(cash['ratio']) > 1
        assert cash['scope'] == 'HISTORICAL_PARTIAL_PROXY_NOT_SUSTAINABILITY_OR_DISTRIBUTABLE_CASH'
