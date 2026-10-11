"""Synthetic source consumption, not issuer or investment acceptance."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json

import pytest

from test_financial_review_attachment import package, _pin
from test_neutral_valuation_proposal import proposal_inputs, run
from value_investment_agent.application.product import financial_valuation_rebase as module
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.valuation_models.residual_income import QualityCompounderFacts


def fixture_rebase(package, monkeypatch):
    root, payload, manifest = package
    payload['financial_period_end'] = '2026-06-30'
    source = payload['source_bindings'][0]
    label = '归属于上市公司股东的扣除非经常性损益的净利润'
    texts = ['归属于母公司所有者权益（或股东权益）合计 1,000.00 900.00',
             '总股本变为100股。', '报告期内，公司股份总数及股本结构未发生变化。',
             label + '200.00100.00', label + '60.0040.00']
    texts[0] += '\n合并资产负债表\n项目 附注 2026年6月30日 2025年12月31日'
    texts.append('2026年半年度报告\n期初余额 期末余额\n股份总数 100.00 100.00')
    facts = []
    for name, page, periods, values in [('fy', 4, ['FY2025', 'FY2024'], ['200', '100']),
                                        ('h1', 5, ['H12026', 'H12025'], ['60', '40'])]:
        facts.append(dict(id=name, label=label, source_id=source['id'], source_binding=deepcopy(source),
            physical_page=page, statement_scope='consolidated_parent_attributable', unit='CNY', currency='CNY',
            evidence_excerpt=texts[page-1], columns=[dict(period=p, value=v) for p, v in zip(periods, values)]))
    payload['facts'] = facts
    payload['calculations'] = {'ttm_ex_nonrecurring_parent_profit': dict(
        formula='FY2025+H12026-H12025', value='220', unit='CNY', scope='consolidated_parent_attributable',
        input_fact_ids=['fy', 'h1', 'h1'], input_column_indices=[0, 0, 1])}
    args = _pin(package)
    monkeypatch.setattr(module, 'extract_pages', lambda path: texts)
    spec = dict(schema_version='financial-proposal-rebase-v1',
        manifest_path='manifest.json', manifest_sha256=args['manifest_sha256'],
        share_basis='DISCLOSED_TOTAL_NOT_TREASURY_OR_DILUTION_ADJUSTED', limitations=['Synthetic only.'])
    for field, value, unit, scope, page in [
            ('start_book_equity', '1000', 'CNY', 'consolidated_parent_attributable', 1),
            ('ordinary_shares', '100', 'shares', 'disclosed_total_ordinary_shares', 2)]:
        spec[field] = dict(value=value, unit=unit, scope=scope, period_end='2026-06-30',
            source_id=source['id'], physical_page=page, evidence_excerpt=texts[page-1])
    spec['share_continuity'] = dict(period_end='2026-06-30', source_id=source['id'], physical_page=3,
                                  evidence_excerpt=texts[2])
    spec['start_book_equity']['evidence_excerpt'] = texts[0].split('\n')[0]
    spec['start_book_equity']['statement_header_page'] = 1
    spec['share_capital_confirmation'] = dict(source_id=source['id'], physical_page=6,
        evidence_excerpt='股份总数 100.00 100.00')
    return root, spec, texts


def call(root, spec):
    facts = QualityCompounderFacts('600887', date(2026, 9, 22), True, '低', [dict(id='old')], [],
                                  operating_inputs={'start_book_equity': Decimal('900'), 'ordinary_shares': Decimal('100')})
    return module.rebase_proposal_facts(root=root, symbol='600887', facts=facts,
        policy=dict(financial_rebase=spec, profit_anchor_field='ttm_ex_nonrecurring_parent_profit_cny'))


def test_bound_inputs_and_full_annual_period_are_consumed(package, monkeypatch):
    root, spec, _ = fixture_rebase(package, monkeypatch)
    facts, anchor, bindings, declaration = call(root, spec)
    assert facts.operating_inputs['start_book_equity'] == Decimal('1000')
    assert anchor == Decimal('220')
    assert facts.as_of == date(2026, 9, 22)
    assert facts.valuation_timing.basis_at.date() == date(2026, 6, 30)
    assert facts.valuation_timing.valuation_at.date() == facts.as_of
    assert declaration['share_basis'].startswith('DISCLOSED_TOTAL')
    assert len(bindings) == 5


@pytest.mark.parametrize('change', ['unit', 'scope', 'period', 'comparative', 'fractional-shares',
                                  'share-amount', 'excerpt', 'share-continuity', 'manifest-hash'])
def test_invalid_capital_cannot_become_model_input(package, monkeypatch, change):
    root, spec, _ = fixture_rebase(package, monkeypatch)
    if change in {'unit', 'scope', 'period'}:
        key = {'unit': 'unit', 'scope': 'scope', 'period': 'period_end'}[change]
        spec['start_book_equity'][key] = 'wrong'
    elif change == 'comparative':
        spec['start_book_equity']['value'] = '900'
    elif change in {'fractional-shares', 'share-amount'}:
        spec['ordinary_shares']['value'] = '100.5' if change == 'fractional-shares' else '101'
    elif change == 'excerpt':
        spec['start_book_equity']['evidence_excerpt'] += 'invented'
    elif change == 'share-continuity':
        spec['share_continuity']['period_end'] = '2025-12-31'
    else:
        spec['manifest_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        call(root, spec)


def test_rebased_profit_and_equity_actually_change_shared_valuation(package, monkeypatch):
    root, spec, _ = fixture_rebase(package, monkeypatch)
    source_package, policy_path = proposal_inputs(root)
    data = json.loads(source_package.read_text(encoding='utf-8'))
    # The baseline's synthetic date is retained, not refreshed to now.
    spec['start_book_equity']['period_end'] = spec['ordinary_shares']['period_end'] = '2026-06-30'
    data['point_in_time']['research_as_of'] = data['point_in_time']['valuation_date'] = '2026-09-22'
    data['research_case']['as_of'] = data['facts']['as_of'] = '2026-09-22'
    source_package.write_text(json.dumps(data), encoding='utf-8')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['source_package_sha256'] = sha256_file(source_package)
    policy['financial_rebase'] = spec
    policy['scenario_conditions'] = {name: dict(cost_of_equity='0.09', retention='0.15', terminal_growth='0')
                                     for name in ('bear', 'base', 'bull')}
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    result = run(root, source_package, policy_path)
    row = result['choices'][0]
    assert row['actual_calculation_inputs']['profit_anchor'] == '220'
    assert row['actual_calculation_inputs']['start_book_equity'] == '1000'
    assert row['valuation']['base_value'] != result['baseline_valuation']['base_value']
    assert result['research_date_advanced'] is result['g3_approved'] is False
    assert row['actual_calculation_inputs']['scenarios']['base']['terminal_roe'] == '0.09'


@pytest.mark.parametrize('change', ['scope', 'unit', 'period', 'column-amount', 'ttm-amount', 'source-availability', 'intraday'])
def test_bound_but_invalid_profit_cannot_be_used(package, monkeypatch, change):
    root, spec, _ = fixture_rebase(package, monkeypatch)
    _, payload, manifest = package
    row = payload['facts'][0]
    if change in {'scope', 'unit'}:
        row['statement_scope' if change == 'scope' else 'unit'] = 'wrong'
    elif change == 'period':
        row['columns'][0]['period'] = 'FY2024'
    elif change == 'column-amount':
        row['columns'][0]['value'] = '201'
        payload['calculations']['ttm_ex_nonrecurring_parent_profit']['value'] = '221'
    elif change == 'ttm-amount':
        payload['calculations']['ttm_ex_nonrecurring_parent_profit']['value'] = '221'
    else:
        source = payload['source_bindings'][0]
        source['available_at_conservative'] = ('2026-09-22T23:59:00+08:00' if change == 'intraday'
                                             else '2026-09-23T00:00:00+08:00')
        manifest['source_bindings'] = deepcopy(payload['source_bindings'])
        for fact in payload['facts']:
            fact['source_binding'] = deepcopy(source)
    spec['manifest_sha256'] = _pin(package)['manifest_sha256']
    with pytest.raises(ValueError):
        call(root, spec)


@pytest.mark.parametrize('change', ['historical-shares', 'annual-equity'])
def test_valid_historical_row_cannot_be_relabeled_current(package, monkeypatch, change):
    root, spec, texts = fixture_rebase(package, monkeypatch)
    if change == 'historical-shares':
        texts[1] += '\n总股本变为90股。'
        spec['ordinary_shares'].update(value='90', evidence_excerpt='总股本变为90股。')
    else:
        texts[0] = texts[0].replace('2026年6月30日 2025年12月31日', '2025年12月31日 2024年12月31日')
    with pytest.raises(ValueError):
        call(root, spec)


def test_equity_bridge_is_consumed_without_changing_inputs_or_admission(package, monkeypatch):
    from test_statement_equity_bridge import synthetic_bridge

    root, spec, texts = fixture_rebase(package, monkeypatch)
    bridge, bridge_pages = synthetic_bridge()
    texts.append(bridge_pages['synthetic'][0])
    bridge['source_id'] = package[1]['source_bindings'][0]['id']
    bridge['header_page'] = 7
    for row in bridge['rows'].values():
        row['physical_page'] = 7
    spec['equity_bridge'] = bridge
    facts, anchor, _, result = call(root, spec)
    assert facts.operating_inputs['start_book_equity'] == Decimal('1000')
    assert anchor == 220
    assert result['equity_bridge_result']['unexplained_difference_cny'] == '0'
    assert result['equity_bridge_result']['future_clean_surplus_assumption_approved'] is False
