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


@pytest.mark.parametrize('costs,spreads,expected', [
    (['.07'] * 3, ['.2', '.21', '.22'], '终端仍假设超额回报持续'),
    (['.10', '.09', '.08'], ['0'] * 3, '永久超额回报归零'),
    (['.07'] * 3, ['-.01', '0', '.01'], '并非全部归零'),
])
def test_mechanism_explanation_uses_current_numbers(costs, spreads, expected):
    rows = [dict(cost_of_equity=cost, terminal_excess_roe=spread)
            for cost, spread in zip(costs, spreads)]
    reasons, limitation = economic._mechanism_explanation(rows)
    assert expected in reasons[1]
    assert ('共用权益成本' in reasons[0]) == (len(set(costs)) == 1)
    assert limitation


def test_mechanism_explanation_rejects_missing_inputs():
    with pytest.raises(ValueError, match='consumed inputs'):
        economic._mechanism_explanation([])


@pytest.mark.parametrize('fault', [None, 'period', 'scope', 'label', 'movement',
    'balance', 'continuity', 'hash', 'future', 'reordered', 'null', 'url'])
def test_parent_cash_balances_use_bound_rows_and_separate_periods(fault):
    labels = ('经营活动产生的现金流量净额', '投资活动产生的现金流量净额',
        '筹资活动产生的现金流量净额', '汇率变动对现金及现金等价物的影响',
        '现金及现金等价物净增加额', '期初现金及现金等价物余额', '期末现金及现金等价物余额')
    facts, calculations = [], {}
    for name, period, values in [
        ('fy_parent_FY2025_cash_residual', 'FY2025', ['10','20','-5','1','26','100','126']),
        ('h1_parent_H12026_cash_residual', 'H12026', ['12','-2','-3','0','7','126','133'])]:
        ids = []
        for index, (label, value) in enumerate(zip(labels, values)):
            identifier = f'{period}-{index}'
            ids.append(identifier)
            facts.append(dict(id=identifier, label=label, source_id=period,
                source_binding=dict(id=period, sha256='a'*64,
                    source_url=f'https://example.invalid/{period}'),
                unit='CNY', currency='CNY', columns=[dict(period=period, value=value)],
                physical_page=10, evidence_excerpt=label + value,
                statement_scope='listed_parent_only'))
        calculations[name] = dict(input_fact_ids=ids, input_column_indices=[0]*7,
            value='0', scope='listed_parent_only', formula='opening+CFO+CFI+CFF+FX-closing')
    if fault == 'period':
        facts[0]['columns'][0]['period'] = 'FY2024'
    elif fault == 'scope':
        facts[0]['statement_scope'] = 'consolidated'
    elif fault == 'label':
        facts[0]['label'] = '营业收入'
    elif fault == 'movement':
        facts[4]['columns'][0]['value'] = '27'
    elif fault == 'balance':
        facts[6]['columns'][0]['value'] = '127'
    elif fault == 'continuity':
        facts[12]['columns'][0]['value'] = '127'
        facts[13]['columns'][0]['value'] = '134'
    elif fault == 'hash':
        facts[0]['source_binding']['sha256'] = 'b'*64
    elif fault == 'null':
        facts[0]['columns'][0]['value'] = None
    elif fault == 'url':
        facts[0]['source_binding']['source_url'] = 'https://example.invalid/forged'
    elif fault == 'future':
        facts[0]['source_binding']['available_at_conservative'] = (NOW + timedelta(days=1)).isoformat()
    elif fault == 'reordered':
        ids = calculations['fy_parent_FY2025_cash_residual']['input_fact_ids']
        ids[0], ids[1] = ids[1], ids[0]
    args = (dict(symbol='600887', facts=facts, calculations=calculations),
            {period: dict(sha256='a'*64, kind='official_issuer_filing',
                location=f'https://example.invalid/{period}')
             for period in ['FY2025', 'H12026']}, '600887', NOW)
    if fault:
        with pytest.raises(ValueError):
            economic._review_calculations(*args)
    else:
        rows = economic._review_calculations(*args)
        assert len(rows) == 2
        assert all(Decimal(row['recomputed_value']) == 0 for row in rows)
        assert rows[1]['evidence'][0]['value'] == '12'
        assert rows[1]['evidence'][0]['label'] == labels[0]


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


@pytest.fixture
def cash_conversion_inputs(tmp_path, monkeypatch):
    """TEST_ONLY source text and amounts, not an approved company valuation."""
    pdf = tmp_path / 'runtime/TEST_ONLY-h1.pdf'
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b'TEST_ONLY source original')
    ref = dict(path=pdf.relative_to(tmp_path).as_posix(), sha256=sha256_file(pdf))
    context = {}
    for name in ('candidate', 'package', 'workbench', 'review_packet'):
        path = tmp_path / 'runtime' / (name + '.json')
        path.write_text('{}', encoding='utf-8')
        context[name + '_binding'] = dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256_file(path))
    for binding in economic._CASH_EXECUTION_BINDINGS:
        target = tmp_path / binding['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((Path(__file__).resolve().parents[1]/binding['path']).read_bytes())
    item = dict(symbol='600519', issuer='贵州茅台', source_id='TEST_ONLY-h1', sha256=ref['sha256'],
        source_url='https://static.cninfo.com.cn/finalpage/2026-08-15/123.PDF',
        periods=['H12026', 'H12025'], published_date='2026-08-15')
    spec_path = tmp_path / 'docs/current/two-company-earnings-bridge-20261024/sources.json'
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps(dict(schema_version='two-company-earnings-source-spec-v1',
        scope='RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION', action='no_order',
        companies={'600519': [item]})), encoding='utf-8')
    source = dict(id=item['source_id'], sha256=ref['sha256'], local_path=ref['path'],
        kind='official_issuer_filing', location=item['source_url'],
        issuer_identity=dict(security_code='600519', issuer_name='贵州茅台'),
        published_at='2026-08-14T16:00:00+00:00',
        source_available_at='2026-09-01T01:00:00+00:00', retrieved_at='2026-09-01T02:00:00+00:00')
    analysis = dict(symbol='600519', source_catalog=[source], source_bindings=[ref, *context.values()],
        review_binding=context, input_descriptor_sha256='a'*64)
    pages = ['公司代码：600519 公司简称：贵州茅台\n2026年半年度报告',
        '合并现金流量表\n2026年1—6月\n单位：元 币种：人民币\n项目 附注 2026年半年度 2025年半年度\n'
        '一、经营活动产生的现金流量：\n经营活动现金流入小计 100.00 80.00',
        '存放中央银行和同业款项净增加额 -4.00 2.00\n经营活动现金流出小计 80.00 68.00\n'
        '经营活动产生的现金流量净额 20.00 12.00\n二、投资活动产生的现金流量：',
        '母公司现金流量表\nTEST_ONLY end boundary']
    monkeypatch.setattr(economic, 'extract_pages', lambda path: list(pages))
    return tmp_path, analysis, pages, pdf, spec_path


def test_cash_conversion_signed_outflow_counterevidence_and_binding(cash_conversion_inputs):
    root, analysis, _, _, _ = cash_conversion_inputs
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE'
    assert result['scope'] == economic._CASH_SCOPE
    assert result['calculation'] == dict(reported_cfo_change_cny='8.00',
        identified_outflow_direction_contribution_cny='6.00',
        contribution_fraction_of_reported_change='0.75',
        current_after_identified_item_cny='16.00', prior_after_identified_item_cny='14.00',
        remaining_change_cny='2.00',
        formula='direction_contribution=prior_outflow-current_outflow; neutral_CFO=CFO+printed_outflow')
    assert [row['physical_page'] for row in result['rows']] == [3, 3]
    assert result['knowledge_as_of'] == '2026-09-01T02:00:00+00:00'
    assert result['candidate_binding'] == analysis['review_binding']['candidate_binding']
    assert result['execution_bindings']
    assert result['normalized_parent_profit_cny'] is None
    assert result['g3_changed'] is result['primary_valuation_usable'] is result['price_admitted'] is False
    assert '不能直接归为' in result['counter_evidence']
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['source_sha', 'source_url', 'source_identity', 'source_issuer', 'source_id', 'unconsumed_path',
    'future', 'missing_clock', 'source_drift', 'execution_drift', 'wrong_code', 'fax_code',
    'wrong_issuer', 'report_year', 'statement_year', 'column_order', 'third_column',
    'unit', 'currency', 'continuation_currency', 'continuation_header', 'parent_only', 'missing_end',
    'one_value', 'duplicate', 'wrong_section'])
def test_cash_conversion_refuses_invalid_sources_and_tables(cash_conversion_inputs, fault):
    root, analysis, pages, pdf, _ = cash_conversion_inputs
    source = analysis['source_catalog'][0]
    if fault == 'source_sha':
        source['sha256'] = 'f'*64
    elif fault == 'source_url':
        source['location'] = 'https://example.invalid/wrong'
    elif fault == 'source_identity':
        source['issuer_identity']['security_code'] = '600887'
    elif fault == 'source_issuer':
        source['issuer_identity']['issuer_name'] = '错误的贵州茅台发行人'
    elif fault == 'source_id':
        source['id'] = 'TEST_ONLY-unbound-other-source'
    elif fault == 'unconsumed_path':
        source['local_path'] = 'runtime/other.pdf'
    elif fault == 'future':
        source['retrieved_at'] = (NOW + timedelta(days=1)).isoformat()
    elif fault == 'missing_clock':
        source['retrieved_at'] = None
    elif fault == 'source_drift':
        pdf.write_bytes(b'drift')
    elif fault == 'execution_drift':
        (root/economic._CASH_EXECUTION_BINDINGS[0]['path']).write_bytes(b'drift')
    elif fault == 'wrong_code':
        pages[0] = pages[0].replace('600519', '600887')
    elif fault == 'fax_code':
        pages[0] = pages[0].replace('公司代码：600519', '电话：010-600519')
    elif fault == 'wrong_issuer':
        pages[0] = pages[0].replace('贵州茅台', '其他公司')
    elif fault == 'report_year':
        pages[0] = pages[0].replace('2026', '2025')
    elif fault == 'statement_year':
        pages[1] = pages[1].replace('2026年1—6月', '2025年1—6月')
    elif fault == 'column_order':
        pages[1] = pages[1].replace('2026年半年度 2025年半年度', '2025年半年度 2026年半年度')
    elif fault == 'third_column':
        pages[1] = pages[1].replace('2025年半年度', '2025年半年度 2024年半年度')
    elif fault == 'unit':
        pages[1] = pages[1].replace('单位：元', '单位：万元')
    elif fault == 'currency':
        pages[1] = pages[1].replace('币种：人民币', '币种：美元')
    elif fault == 'continuation_currency':
        pages[2] = '币种：美元\n' + pages[2]
    elif fault == 'continuation_header':
        pages[2] = '项目 附注 2024年半年度 2023年半年度\n' + pages[2]
    elif fault == 'parent_only':
        pages[1] = pages[1].replace('合并现金流量表', '母公司现金流量表')
    elif fault == 'missing_end':
        pages[3] = 'end without identified table boundary'
    elif fault == 'one_value':
        pages[2] = pages[2].replace('-4.00 2.00', '-4.00')
    elif fault == 'duplicate':
        pages[2] += '\n经营活动产生的现金流量净额 20.00 12.00'
    elif fault == 'wrong_section':
        pages[1] = pages[1].replace('经营活动现金流入小计',
            '存放中央银行和同业款项净增加额 -4.00 2.00\n经营活动现金流入小计')
        pages[2] = pages[2].replace('存放中央银行和同业款项净增加额 -4.00 2.00\n', '')
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] in {'UNAVAILABLE', 'SOURCES_DIFFER_FROM_CURRENT_RESEARCH'}
    assert result['reason'] and result['rows'] == [] and result['calculation'] is None
    assert result['normalized_parent_profit_cny'] is None and result['g3_changed'] is False


@pytest.mark.parametrize('target', ['source', 'spec', 'candidate', 'execution'])
def test_cash_conversion_rechecks_closure_after_read(cash_conversion_inputs, monkeypatch, target):
    root, analysis, pages, pdf, spec_path = cash_conversion_inputs
    def extract(path):
        changed = {'source': pdf, 'spec': spec_path,
            'candidate': root/analysis['review_binding']['candidate_binding']['path'],
            'execution': root/economic._CASH_EXECUTION_BINDINGS[0]['path']}[target]
        changed.write_bytes(changed.read_bytes() + b'drift')
        return list(pages)
    monkeypatch.setattr(economic, 'extract_pages', extract)
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'UNAVAILABLE' and result['calculation'] is None


def test_cash_conversion_zero_change_does_not_invent_ratio(cash_conversion_inputs):
    root, analysis, pages, _, _ = cash_conversion_inputs
    pages[2] = pages[2].replace('20.00 12.00', '12.00 12.00')
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE'
    assert result['calculation']['contribution_fraction_of_reported_change'] is None


@pytest.mark.parametrize('heading', ['子公司现金流量表', '其他主体现金流量表',
    '编制单位：其他公司', '编制单位：非贵州茅台公司'])
def test_cash_conversion_rejects_changed_continuation_owner(cash_conversion_inputs, heading):
    root, analysis, pages, _, _ = cash_conversion_inputs
    pages[2] = heading + '\n' + pages[2]
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert result['calculation'] is None and result['rows'] == []
    assert any(reason in result['reason'] for reason in (
        'STATEMENT_OWNERSHIP_CHANGED', 'COMPILING_ENTITY_MISMATCH'))


@pytest.mark.parametrize('explicit_continuation', [False, True])
def test_cash_conversion_preserves_same_entity_cross_page(cash_conversion_inputs, explicit_continuation):
    root, analysis, pages, _, _ = cash_conversion_inputs
    if explicit_continuation:
        pages[0] += '\n贵州茅台酒股份有限公司2026年半年度报告'
        pages[2] = '合并现金流量表（续）\n编制单位：贵州茅台酒股份有限公司\n' + pages[2]
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE'
    assert result['calculation']['identified_outflow_direction_contribution_cny'] == '6.00'
    assert result['calculation']['contribution_fraction_of_reported_change'] == '0.75'
    for row in result['rows']:
        evidence = row['statement_ownership_evidence']
        assert evidence[0]['kind'] == 'CONSOLIDATED_TABLE_START'
        if explicit_continuation:
            assert {item['kind'] for item in evidence} == {
                'CONSOLIDATED_TABLE_START', 'CONSOLIDATED_CONTINUATION', 'MATCHED_COMPILING_ENTITY'}


def test_cash_conversion_decline_keeps_signed_ratio_and_neutral_explanation(cash_conversion_inputs):
    root, analysis, pages, _, _ = cash_conversion_inputs
    pages[2] = pages[2].replace('20.00 12.00', '4.00 12.00')
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['calculation']['reported_cfo_change_cny'] == '-8.00'
    assert result['calculation']['contribution_fraction_of_reported_change'] == '-0.75'
    assert '同比变化' in result['counter_evidence']


def test_cash_conversion_blank_financial_template_is_not_zero(cash_conversion_inputs):
    root, analysis, pages, _, _ = cash_conversion_inputs
    pages[2] = pages[2].replace('-4.00 2.00', '')
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'NOT_APPLICABLE'
    assert 'NOT_ASSUMED_ZERO' in result['reason']
    assert result['rows'] == [] and result['calculation'] is None


def test_cash_conversion_has_no_security_specific_rule(cash_conversion_inputs):
    root, analysis, pages, _, spec_path = cash_conversion_inputs
    spec = json.loads(spec_path.read_bytes())
    declared = spec['companies'].pop('600519')
    declared[0]['symbol'] = '000001'
    spec['companies']['000001'] = declared
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    analysis['symbol'] = '000001'
    analysis['source_catalog'][0]['issuer_identity']['security_code'] = '000001'
    pages[0] = pages[0].replace('600519', '000001')
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE'
    assert result['symbol'] == '000001'


def test_cash_conversion_source_cannot_predate_report_period(cash_conversion_inputs):
    root, analysis, pages, _, spec_path = cash_conversion_inputs
    spec = json.loads(spec_path.read_bytes())
    spec['companies']['600519'][0]['periods'] = ['H12027', 'H12026']
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    pages[0] = pages[0].replace('2026', '2027')
    pages[1] = pages[1].replace('2026', '2027').replace('2025', '2026')
    result = economic._current_cash_conversion_diagnostic(root, analysis, NOW)
    assert result['status'] == 'UNAVAILABLE' and result['calculation'] is None
    assert 'CLOCK_INVALID' in result['reason']


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
        diagnostic = result['cash_conversion_diagnostic']
        assert diagnostic['status'] == 'SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE'
        assert diagnostic['scope'] == economic._CASH_SCOPE
        calculation = diagnostic['calculation']
        assert calculation['reported_cfo_change_cny'] == '57571689087.73'
        assert calculation['identified_outflow_direction_contribution_cny'] == '47306240453.43'
        assert calculation['current_after_identified_item_cny'] == '48795297834.88'
        assert calculation['prior_after_identified_item_cny'] == '38529849200.58'
        assert Decimal(calculation['contribution_fraction_of_reported_change']) > Decimal('.82')
        assert [row['physical_page'] for row in diagnostic['rows']] == [34, 34]
        assert all(ref in result['source_bindings'] for ref in diagnostic['execution_bindings'])
        assert all(ref in result['source_bindings'] for ref in diagnostic['source_bindings'])
        assert diagnostic['knowledge_as_of'] == diagnostic['source_retrieved_at']
        assert not diagnostic['historical_pit_admitted'] and not diagnostic['g3_changed']
        assert review['status'] == 'HISTORICAL_BRIDGES_REPLAYED_NOT_ECONOMIC_APPROVAL'
        assert len(review['bridge_results']) == 6
        assert len(review['unknown_fields']) == 13
        assert all(Decimal(row['difference_cny']) == 0 for row in review['bridge_results'])
        assert result['model_applicability']['clean_surplus_bridge'] is None
        assert 'SUSTAINABLE_DISTRIBUTABLE_CASH_NOT_ESTABLISHED' in result['blockers']
        assert result['earnings']['historical_bridge']['computed_ttm_cny'] == '81367067677.44'
        assert result['model_applicability']['assessment'] == 'CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION'
        assert '共用权益成本' in result['model_applicability']['reasons'][0]
        assert '终端仍假设超额回报持续' in result['model_applicability']['reasons'][1]
        assert 'Positive terminal excess returns' in result['model_applicability']['limitation']
    else:
        diagnostic = result['cash_conversion_diagnostic']
        assert diagnostic['status'] == 'NOT_APPLICABLE'
        assert diagnostic['calculation'] is None and diagnostic['rows'] == []
        assert 'NOT_ASSUMED_ZERO' in diagnostic['reason']
        assert review['status'] == 'NO_SUPPORTED_BOUND_BRIDGE'
        assert review['coverage_status'] == 'NOT_COVERED_UNKNOWN_COMPLETENESS_NOT_ASSESSED'
        assert result['model_applicability']['clean_surplus_bridge'] is not None
        assert result['model_applicability']['assessment'] == 'STRESS_ONLY'
        assert '永久超额回报归零' in result['model_applicability']['reasons'][1]
        assert result['historical_cash_observations']
        bridges = {row['id']: row for row in result['historical_cash_observations']
                   if row['id'].endswith('_cash_residual')}
        assert len(bridges) == 2
        assert bridges['fy_parent_FY2025_cash_residual']['evidence'][6]['value'] == '13404587376.75'
        assert bridges['h1_parent_H12026_cash_residual']['evidence'][6]['value'] == '14939427794.14'
        assert all(row['explicit_years'] == 4 for row in result['scenarios'])
        assert result['earnings']['historical_bridge']['computed_ttm_cny'] == '9647734710.01'
        cash, = result['cash_return_diagnostics']
        assert cash['difference_cny'] == '800308192.72'
        assert Decimal(cash['ratio']) > 1
        assert cash['scope'] == 'HISTORICAL_PARTIAL_PROXY_NOT_SUSTAINABILITY_OR_DISTRIBUTABLE_CASH'
