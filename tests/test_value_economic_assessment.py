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


@pytest.mark.parametrize('fault', [None, 'wrongperiod', 'reorder', 'duplicate', 'wrongprofitbasis'])
def test_ttm_requires_ordered_distinct_periods_and_disclosed_profit_basis(fault):
    label = ('\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684'
             '\u6263\u9664\u975e\u7ecf\u5e38\u6027\u635f\u76ca\u7684\u51c0\u5229\u6da6')
    facts = [dict(id=identifier, label=label, source_id='official',
        source_binding=dict(id='official', sha256='a'*64),
        unit='CNY', currency='CNY', statement_scope='consolidated_parent_attributable',
        physical_page=page, evidence_excerpt=label + ' amounts',
        columns=[dict(period=p, value='100') for p in periods])
        for identifier, page, periods in [('arbitrary_annual', 7, ['FY2025', 'FY2024']),
                                        ('arbitrary_interim', 6, ['H12026', 'H12025'])]]
    calc = dict(input_fact_ids=['arbitrary_annual', 'arbitrary_interim', 'arbitrary_interim'],
        input_column_indices=[0, 0, 1], value='100', formula='FY2025+H12026-H12025')
    review = dict(symbol='600887', facts=facts, calculations=dict(ttm_ex_nonrecurring_parent_profit=calc))
    if fault == 'wrongperiod':
        for fact in facts:
            for column in fact['columns']:
                column['period'] = 'FY2024'
    if fault == 'reorder':
        calc['input_fact_ids'][:2] = list(reversed(calc['input_fact_ids'][:2]))
    if fault == 'duplicate':
        calc['input_column_indices'][2] = 0
    if fault == 'wrongprofitbasis':
        facts[0]['label'] = '\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da6'
        facts[0]['evidence_excerpt'] = facts[0]['label']
    if fault:
        with pytest.raises(ValueError, match='TTM calculation requires'):
            economic._review_calculations(review, {'official': dict(sha256='a'*64)}, '600887', NOW)
    else:
        row, = economic._review_calculations(review, {'official': dict(sha256='a'*64)}, '600887', NOW)
        assert row['recomputed_value'] == '100'


def test_accounting_integration_reuses_registered_analysis_once(registered, monkeypatch):
    from value_investment_agent.application.research import economic_review_bundle
    root, symbol, _, _ = registered
    original = economic.load_current_value_research_analysis
    calls = []
    def counted(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    def duplicate(**kwargs):
        pytest.fail('Accounting integration must not reload or recalculate the model')
    monkeypatch.setattr(economic, 'load_current_value_research_analysis', counted)
    monkeypatch.setattr(economic_review_bundle, 'load_current_value_research_analysis', duplicate)
    result = economic.load_current_value_economic_assessment(root=root, symbol=symbol, now=NOW)
    review = result['accounting_bridge_review']
    assert len(calls) == 1
    assert review['input_descriptor_sha256'] == result['input_descriptor_sha256']
    assert review['review_binding'] == result['review_binding']
    assert 'evaluated_at' not in review
    assert review['status'] == 'NO_SUPPORTED_BOUND_BRIDGE'
    assert review['coverage_status'] == 'NOT_COVERED_UNKNOWN_COMPLETENESS_NOT_ASSESSED'
    assert review['economic_approval_granted'] is False


def test_accounting_integration_rejects_different_descriptor(registered, monkeypatch):
    root, symbol, _, _ = registered
    original = economic.load_current_value_research_analysis
    def wrong_version(**kwargs):
        result = original(**kwargs)
        result['input_descriptor_sha256'] = 'f' * 64
        return result
    monkeypatch.setattr(economic, 'load_current_value_research_analysis', wrong_version)
    with pytest.raises(ValueError, match='descriptor'):
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
    review = result['accounting_bridge_review']
    assert review['input_descriptor_sha256'] == result['input_descriptor_sha256']
    assert review['review_binding'] == result['review_binding']
    assert 'evaluated_at' not in review
    assert review['primary_valuation_usable'] is review['economic_approval_granted'] is False
    assert review['approval_changed'] is False
    if symbol == '600519':
        assert review['status'] == 'HISTORICAL_BRIDGES_REPLAYED_NOT_ECONOMIC_APPROVAL'
        assert len(review['bridge_results']) == 6
        assert len(review['unknown_fields']) == 13
        assert all(Decimal(row['difference_cny']) == 0 for row in review['bridge_results'])
        assert result['model_applicability']['clean_surplus_bridge'] is None
        assert 'SUSTAINABLE_DISTRIBUTABLE_CASH_NOT_ESTABLISHED' in result['blockers']
        assert result['earnings']['historical_bridge']['computed_ttm_cny'] == '81367067677.44'
        assert result['model_applicability']['assessment'] == 'CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION'
    else:
        assert review['status'] == 'NO_SUPPORTED_BOUND_BRIDGE'
        assert review['coverage_status'] == 'NOT_COVERED_UNKNOWN_COMPLETENESS_NOT_ASSESSED'
        assert result['model_applicability']['clean_surplus_bridge'] is not None
        assert result['model_applicability']['assessment'] == 'STRESS_ONLY'
        assert result['historical_cash_observations']
        assert all(row['explicit_years'] == 4 for row in result['scenarios'])
        assert result['earnings']['historical_bridge']['computed_ttm_cny'] == '9647734710.01'
        cash, = result['cash_return_diagnostics']
        assert cash['difference_cny'] == '800308192.72'
        assert Decimal(cash['ratio']) > 1
        assert cash['scope'] == 'HISTORICAL_PARTIAL_PROXY_NOT_SUSTAINABILITY_OR_DISTRIBUTABLE_CASH'
