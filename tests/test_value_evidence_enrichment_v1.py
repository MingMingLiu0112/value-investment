from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib

import pytest

from value_investment_agent.application.research.value_evidence_enrichment_v1 import (
    enrich_retained_company, validate_debt_scope,
)
from value_investment_agent.financial_quality import GENERAL_FIELDS
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as adapter

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def components():
    rows = []
    for field in adapter.DEBT_LABELS:
        rows.append(dict(symbol='600887', field_name=field, period_label='2025-12-31',
                         value='10', unit='CNY', data_point_id=field, source_id='official',
                         created_at='2026-09-01T00:00:00+00:00',
                         published_at='2026-04-30T00:00:00+00:00',
                         fetched_at='2026-09-01T00:00:00+00:00', validation_status='verified',
                         metadata=dict(automatic_cross_source_verification=True,
                                       currency='CNY', statement_scope='consolidated',
                                       debt_scope_reviewed=True, classification_reason='TEST_ONLY reviewed note',
                                       secondary_data_point_id='secondary-' + field,
                                       secondary_source_id='secondary',
                                       secondary_source_url='https://vip.stock.finance.sina.com.cn/test',
                                       verification_method='official_pdf_plus_independent_structured_source',
                                       debt_scope_reviewed_at='2026-09-01T00:00:00+00:00',
                                       debt_classification='scope_review' if field == 'other_financing_scope' else 'included',
                                       other_financing_exhaustive=True, noncurrent_only=True,
                                       debt_only_including_current_leases=True, financing_only=True,
                                       official_evidence=dict(sha256='a' * 64, page=1,
                                                             source_url='https://static.cninfo.com.cn/test.pdf',
                                                             excerpt='TEST_ONLY amount 10'))))
    return rows


def test_complete_scope_counts_each_bucket_once_without_scope_review_amount():
    result = validate_debt_scope('600887', '2025-12-31', components(), evaluation_at=NOW)
    assert result['scope_contract_complete'] is True
    assert result['complete_debt_verified'] is False
    assert result['value'] == '80'
    assert result['automatic_cross_source_verification_created'] is False


def _funding_observation(value='10', prior='10'):
    return dict(field_name='financial_deposits_and_interbank', value=value, prior_value=prior,
        period_label='2025-12-31', prior_period_label='2024-12-31', unit='CNY', currency='CNY',
        statement_scope='consolidated', page=1, excerpt='TEST_ONLY funding 10',
        status='CANDIDATE_SOURCE_UNVERIFIED')


def test_financial_requirements_cannot_be_replaced_by_other_scope_review():
    result = validate_debt_scope('600887', '2025-12-31', components(), evaluation_at=NOW,
        financial_funding_requirements=[_funding_observation()])
    assert result['value'] is None and not result['scope_contract_complete']
    assert 'MISSING_COMPONENT:financial_deposits_and_interbank' in result['issues']


@pytest.mark.parametrize('damage', ['missing_amount', 'scope_review', 'future', 'no_secondary',
    'unknown_current', 'wrong_amount', 'wrong_period', 'wrong_unit'])
def test_financial_component_uses_existing_classification_time_and_correlation_gates(damage):
    rows = components()
    financial = deepcopy(rows[0])
    financial.update(field_name='financial_deposits_and_interbank', data_point_id='financial')
    observed = _funding_observation()
    if damage == 'missing_amount': financial['value'] = None
    elif damage == 'scope_review': financial['metadata']['debt_classification'] = 'scope_review'
    elif damage == 'future': financial['metadata']['debt_scope_reviewed_at'] = '2027-01-01T00:00:00+00:00'
    elif damage == 'no_secondary': financial['metadata'].pop('secondary_data_point_id')
    elif damage == 'unknown_current': observed['value'] = None
    elif damage == 'wrong_amount': financial['value'] = '9'
    elif damage == 'wrong_period': observed['period_label'] = '2026-06-30'
    elif damage == 'wrong_unit': observed['unit'] = 'CNY_10000'
    result = validate_debt_scope('600887', '2025-12-31', rows+[financial], evaluation_at=NOW,
        financial_funding_requirements=[observed])
    assert result['value'] is None and result['complete_debt_verified'] is False
    assert not result['scope_contract_complete']


def test_explicit_financial_component_is_not_an_unexpected_or_ignored_field():
    rows = components()
    financial = deepcopy(rows[0])
    financial.update(field_name='financial_deposits_and_interbank', data_point_id='financial')
    result = validate_debt_scope('600887', '2025-12-31', rows+[financial], evaluation_at=NOW)
    assert result['scope_contract_complete'] and result['value'] == '90'
    assert not result['complete_debt_verified']  # Still requires actual original/secondary bytes.


@pytest.mark.parametrize('mutation,issue', [
    (lambda r: r.pop(), 'MISSING_COMPONENT'),
    (lambda r: r.append(deepcopy(r[0])), 'DUPLICATE_COMPONENT'),
    (lambda r: r[0].update(value='NaN'), 'INVALID_AMOUNT'),
    (lambda r: r[0].update(value='-1'), 'INVALID_AMOUNT'),
    (lambda r: r[0].update(period_label='2026-06-30'), 'IDENTITY_OR_PERIOD'),
    (lambda r: r[0].update(symbol='600519'), 'IDENTITY_OR_PERIOD'),
    (lambda r: r[0].update(unit='CNY 100M'), 'UNIT_CURRENCY'),
    (lambda r: r[0]['metadata'].update(statement_scope='parent'), 'UNIT_CURRENCY'),
    (lambda r: r[0]['metadata'].update(evidence_quarantine=True), 'UNVERIFIED'),
    (lambda r: r[0]['metadata'].update(financing_only=False), 'OPERATING_LIABILITIES'),
    (lambda r: r[1]['metadata'].update(debt_only_including_current_leases=False), 'CURRENT_MATURITIES'),
    (lambda r: r[4]['metadata'].update(noncurrent_only=False), 'DOUBLE_COUNT'),
    (lambda r: r[-1]['metadata'].update(other_financing_exhaustive=False), 'EXHAUSTIVELY'),
    (lambda r: r[0]['metadata'].update(debt_scope_reviewed_at='2027-01-01T00:00:00+00:00'), 'CUTOFF'),
    (lambda r: r[0]['metadata'].pop('official_evidence'), 'MISSING_OFFICIAL'),
])
def test_scope_fails_closed(mutation, issue):
    rows = components()
    mutation(rows)
    result = validate_debt_scope('600887', '2025-12-31', rows, evaluation_at=NOW)
    assert result['complete_debt_verified'] is False
    assert result['value'] is None
    assert any(issue in reason for reason in result['issues'])


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / 'annual.pdf'
    path.write_bytes(b'TEST_ONLY retained original')
    pages = ['\u80a1\u7968\u4ee3\u7801: 600887; 2025\u5e74\u5e74\u5ea6\u62a5\u544a TEST_ONLY amount 10']
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    monkeypatch.setattr(adapter, 'extract_candidates_from_pages', lambda pages: [])
    return adapter.RetainedAnnualSource('600887', '2025-12-31', 'annual.pdf',
                                        hashlib.sha256(path.read_bytes()).hexdigest(),
                                        'https://static.cninfo.com.cn/test.pdf',
                                        '2026-09-01T00:00:00+00:00')


def test_retained_extraction_cache_hash_and_budget(tmp_path, source):
    kwargs = dict(evaluation_at=NOW, cache_dir=tmp_path / '.tmp/cache')
    first = adapter.extract_retained_annual(tmp_path, source, **kwargs)
    second = adapter.extract_retained_annual(tmp_path, source, **kwargs)
    assert not first['reused'] and second['reused']
    assert all(s['status'] == 'NOT_LOCATED_NOT_ZERO' for s in first['debt_searches'].values())
    with pytest.raises(ValueError, match='byte budget'):
        adapter.extract_retained_annual(tmp_path, source, max_bytes=1, **kwargs)
    (tmp_path / 'annual.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        adapter.extract_retained_annual(tmp_path, source, **kwargs)


def test_financial_admission_rejects_self_resealed_extraction_cache(tmp_path, source):
    import json
    cache = tmp_path / '.tmp/cache'
    adapter.extract_retained_annual(tmp_path, source, evaluation_at=NOW, cache_dir=cache)
    path = next(cache.glob('*.json'))
    envelope = json.loads(path.read_bytes())
    envelope['packet']['income_comparatives'] = [dict(field_name='revenue', value='999')]
    envelope['packet_sha256'] = hashlib.sha256(
        json.dumps(envelope['packet'], sort_keys=True).encode()).hexdigest()
    path.write_text(json.dumps(envelope), encoding='utf-8')
    with pytest.raises(ValueError, match='original re-extraction'):
        enrich_retained_company(tmp_path, source, [], evaluation_at=NOW, cache_dir=cache)


def test_company_information_code_on_page_six_is_verified_not_guessed(tmp_path, source, monkeypatch):
    pages = ['2025\u5e74\u5e74\u5ea6\u62a5\u544a'] + ['contents'] * 4 + ['\u80a1\u7968\u4ee3\u7801 600887']
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    result = adapter.extract_retained_annual(tmp_path, source, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/six')
    assert result['page_count'] == 6
    pages[-1] = '\u80a1\u7968\u4ee3\u7801 000589; reference 600887'
    with pytest.raises(ValueError, match='labelled security identity'):
        adapter.extract_retained_annual(tmp_path, source, evaluation_at=NOW,
            cache_dir=tmp_path / '.tmp/wrong')


def test_future_original_and_path_escape_rejected(tmp_path, source):
    with pytest.raises(ValueError, match='cutoff'):
        adapter.extract_retained_annual(tmp_path, source, evaluation_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                       cache_dir=tmp_path / '.tmp/cache')
    with pytest.raises(ValueError, match='outside repository'):
        adapter._inside(tmp_path, '../escape.pdf')


def test_real_missing_components_never_promote_pending_aggregate(tmp_path, source):
    debt = dict(symbol='600887', field_name='interest_bearing_debt', period_label='2025-12-31',
                value='80', unit='CNY', data_point_id='debt', created_at='2026-09-01T00:00:00+00:00',
                validation_status='pending', metadata={})
    points = [debt]
    before = deepcopy(points)
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
                                     cache_dir=tmp_path / '.tmp/cache')
    assert result['after']['total_score'] is None
    assert result['debt_scope']['value'] is None
    assert result['adopted_debt_fact_ids'] == []
    assert points == before


def _complete_points(tmp_path, source):
    rows = components()
    for row in rows:
        row['metadata']['official_evidence']['sha256'] = source.sha256
    points = []
    for field in GENERAL_FIELDS:
        row = deepcopy(rows[0])
        row.update(field_name=field, data_point_id=field,
                   value='80' if field == 'interest_bearing_debt' else '20',
                   unit='CNY' if field in {'cash', 'interest_bearing_debt'} else 'percent')
        points.append(row)
    for row in rows:
        second = deepcopy(row)
        backing = tmp_path / ('secondary-' + row['field_name'] + '.json')
        backing.write_text('TEST_ONLY independent retained structured source ' + row['field_name'], encoding='utf-8')
        second.update(data_point_id='secondary-' + row['field_name'], source_id='secondary',
                      source_url='https://vip.stock.finance.sina.com.cn/test',
                      source_name='AkShare / Sina detailed financial statements',
                      source_path=str(backing.relative_to(tmp_path)),
                      sha256=hashlib.sha256(backing.read_bytes()).hexdigest())
        points.append(second)
    points.extend(deepcopy(rows))
    return points, rows


def _funding_pages(monkeypatch, current='10.00', prior='10.00'):
    # TEST_ONLY original-decoder seam; real helper and all admission gates run.
    page = ('股票代码: 600887; 2025年年度报告 TEST_ONLY amount 10\n'
            '合并资产负债表\n单位：元 币种：人民币\n'
            '项目 2025年12月31日 2024年12月31日\n'
            f'吸收存款及同业存放 {current} {prior}\n')
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: [page][:limit])
    return page.splitlines()[-1]


def _financial_points(tmp_path, source, excerpt):
    points, rows = _complete_points(tmp_path, source)
    field = 'financial_deposits_and_interbank'
    primary = deepcopy(rows[0])
    primary.update(field_name=field, data_point_id=field, value='10')
    primary['metadata'].update(secondary_data_point_id='secondary-' + field,
        official_evidence=dict(sha256=source.sha256, page=1, source_url=source.source_url, excerpt=excerpt))
    second = deepcopy(primary)
    backing = tmp_path / 'TEST_ONLY-financial-secondary.json'
    backing.write_text('TEST_ONLY Sina structured funding 10', encoding='utf-8')
    second.update(data_point_id='secondary-' + field, source_id='secondary',
        source_url='https://vip.stock.finance.sina.com.cn/test',
        source_name='AkShare / Sina detailed financial statements',
        source_path=backing.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(backing.read_bytes()).hexdigest())
    points.extend([deepcopy(primary), second])
    for point in points:
        if point['field_name'] == 'interest_bearing_debt':
            point['value'] = '90'
    return points, rows+[primary]


@pytest.mark.parametrize('automatic', [True, False])
def test_observed_financial_funding_blocks_false_complete_with_only_nine_buckets(tmp_path, source, monkeypatch, automatic):
    _funding_pages(monkeypatch)
    points, rows = _complete_points(tmp_path, source)
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/funding', **({} if automatic else dict(components=rows)))
    assert not result['debt_scope']['complete_debt_verified']
    assert result['debt_scope']['value'] is None
    assert 'MISSING_COMPONENT:financial_deposits_and_interbank' in result['debt_scope']['issues']
    assert result['adopted_debt_fact_ids'] == [] and result['after']['total_score'] is None
    diagnostic = result['source_financial_funding_scope']
    assert diagnostic['symbol'] == source.symbol
    assert diagnostic['required_fields'] == diagnostic['unresolved_fields'] == ['financial_deposits_and_interbank']
    assert diagnostic['financial_fact_admitted'] is False


@pytest.mark.parametrize('automatic', [True, False])
def test_financial_funding_full_scope_requires_and_preserves_bound_independent_evidence(tmp_path, source, monkeypatch, automatic):
    excerpt = _funding_pages(monkeypatch)
    points, rows = _financial_points(tmp_path, source, excerpt)
    before = deepcopy(points)
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/funding-positive', **({} if automatic else dict(components=rows)))
    assert result['debt_scope']['complete_debt_verified'], result['debt_scope']['issues']
    assert result['debt_scope']['value'] == '90'
    assert len(result['adopted_debt_fact_ids']) == 1
    assert result['source_financial_funding_scope']['unresolved_fields'] == []
    assert result['source_financial_funding_scope']['financial_fact_admitted'] is False
    assert points == before


@pytest.mark.parametrize('damage', ['secondary_hash', 'secondary_future', 'secondary_pending',
    'primary_amount', 'primary_excluded_amount', 'source_unknown', 'no_source_observation'])
def test_financial_funding_cannot_bypass_original_amount_independence_or_time(tmp_path, source, monkeypatch, damage):
    excerpt = _funding_pages(monkeypatch)
    points, rows = _financial_points(tmp_path, source, excerpt)
    if damage.startswith('secondary'):
        second = next(p for p in points if p['data_point_id'] == 'secondary-financial_deposits_and_interbank')
        if damage == 'secondary_hash': second['sha256'] = 'f'*64
        elif damage == 'secondary_future': second['available_at'] = '2027-01-01T00:00:00+00:00'
        else: second['validation_status'] = 'pending'
    elif damage in {'primary_amount', 'primary_excluded_amount'}:
        for primary in [rows[-1], next(p for p in points if p['data_point_id'] == 'financial_deposits_and_interbank')]:
            primary['value'] = '9'
            if damage == 'primary_excluded_amount': primary['metadata']['debt_classification'] = 'excluded'
    elif damage == 'source_unknown': _funding_pages(monkeypatch, current='--')
    elif damage == 'no_source_observation':
        monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: ['股票代码: 600887; 2025年年度报告 TEST_ONLY amount 10'])
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/funding-negative', components=rows)
    assert not result['debt_scope']['complete_debt_verified']
    assert result['debt_scope']['value'] is None
    assert result['adopted_debt_fact_ids'] == []


@pytest.mark.parametrize('cell', ['10.00', '100', '28', '七(30)'])
def test_unknown_single_column_is_required_but_blank_templates_are_not(tmp_path, source, monkeypatch, cell):
    _funding_pages(monkeypatch, current=cell, prior='')
    points, rows = _complete_points(tmp_path, source)
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/one-column', components=rows)
    assert result['source_financial_funding_scope']['required_fields'] == ['financial_deposits_and_interbank']
    assert not result['debt_scope']['complete_debt_verified']
    _funding_pages(monkeypatch, current='--', prior='--')
    blank = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/blank', components=rows)
    assert blank['source_financial_funding_scope']['required_fields'] == []
    assert blank['debt_scope']['complete_debt_verified']


def test_existing_incomplete_industrial_scope_is_unchanged_with_adjacent_alert(tmp_path, source, monkeypatch):
    baseline = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/no-funding')
    _funding_pages(monkeypatch)
    result = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/new-funding')
    assert result['debt_scope'] == baseline['debt_scope']
    assert result['adopted_points'] == baseline['adopted_points']
    assert result['after'] == baseline['after']
    assert result['source_financial_funding_scope']['required_fields'] == ['financial_deposits_and_interbank']


def test_funding_cash_research_context_is_source_bound_and_does_not_adopt_facts(tmp_path, source, monkeypatch):
    from test_financial_funding_scope import context_pages
    baseline = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/context-baseline')
    pages = ['\u80a1\u7968\u4ee3\u7801: 600887; 2025\u5e74\u5e74\u5ea6\u62a5\u544a TEST_ONLY'] + context_pages()
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    result = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/context')
    context = result['source_financial_funding_scope']['research_context']
    assert context['status'] == 'SOURCE_BOUND_RESEARCH_OBSERVATIONS'
    assert context['symbol'] == source.symbol and context['period_label'] == source.period
    assert context['source_binding']['sha256'] == source.sha256
    assert context['source_binding']['path'] == source.path
    assert context['financial_fact_admitted'] is context['formal_eligibility'] is False
    assert len(context['observations']) == 4
    ids = {row['observation_id'] for row in context['observations']}
    ratio, = context['derivations']
    assert ratio['value'] == '0.4' and ratio['unit'] == 'ratio'
    assert set(ratio['input_observation_ids']) <= ids
    assert ratio['evidence_kind'] == 'DERIVED_RESEARCH_OBSERVATION'
    for row in context['observations']:
        assert row['source_binding'] == context['source_binding']
        assert row['symbol'] == source.symbol and row['period_label'] == source.period
        assert row['available_at'] == source.available_at and row['page'] > 0
        assert row['excerpt'] in pages[row['page']-1]
        assert row['financial_fact_admitted'] is False and row['action'] == 'no_order'
    assert result['adopted_points'] == baseline['adopted_points']
    assert result['after'] == baseline['after'] and result['debt_scope']['value'] is None
    assert context['missing_fields'] == []


@pytest.mark.parametrize('fault', ['hash', 'company', 'period', 'future'])
def test_funding_cash_context_cannot_bypass_existing_original_identity_or_time(tmp_path, source, monkeypatch, fault):
    from dataclasses import replace
    from test_financial_funding_scope import context_pages
    pages = ['\u80a1\u7968\u4ee3\u7801: 600887; 2025\u5e74\u5e74\u5ea6\u62a5\u544a TEST_ONLY'] + context_pages()
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    changes = {'hash': dict(sha256='f'*64), 'company': dict(symbol='600519'),
               'period': dict(period='2024-12-31'), 'future': dict(available_at='2027-01-01T00:00:00+00:00')}
    with pytest.raises(ValueError):
        enrich_retained_company(tmp_path, replace(source, **changes[fault]), [], evaluation_at=NOW,
            cache_dir=tmp_path/'.tmp/context-negative')


def test_funding_cash_partial_evidence_has_no_ratio_or_fabricated_cash(tmp_path, source, monkeypatch):
    _funding_pages(monkeypatch)
    result = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/context-partial')
    context = result['source_financial_funding_scope']['research_context']
    assert context['status'] == 'PARTIAL' and context['derivations'] == []
    assert {row['field_name'] for row in context['observations']} == {'financial_deposits_and_interbank'}
    assert set(context['missing_fields']) == {'controlling_group_deposits',
        'consolidated_cash_and_equivalents', 'issuer_parent_cash_and_equivalents'}


def test_funding_cash_context_does_not_compute_concentration_above_total(tmp_path, source, monkeypatch):
    from test_financial_funding_scope import context_pages
    pages = ['\u80a1\u7968\u4ee3\u7801: 600887; 2025\u5e74\u5e74\u5ea6\u62a5\u544a TEST_ONLY'] + context_pages()
    pages[1] = pages[1].replace('100.00 90.00', '10.00 9.00')
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    result = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
        cache_dir=tmp_path/'.tmp/context-inconsistent')
    context = result['source_financial_funding_scope']['research_context']
    assert context['derivations'] == [] and context['status'] == 'PARTIAL'
    assert context['blockers'] == ['CONCENTRATION_INPUTS_INCONSISTENT']


@pytest.mark.parametrize('period,filing,expected_hash,numerator,denominator', [
    ('2025-12-31', '1225114741', '474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288',
     '8330698318.34', '18038383776.30'),
    ('2026-06-30', '1225475868', '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6',
     '15158632454.02', '25426316668.17'),
])
def test_real_funding_cash_context_closure_not_h1_annual_admission(tmp_path, period, filing,
        expected_hash, numerator, denominator):
    import os
    from pathlib import Path
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import _source_financial_funding_scope
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    raw_root = os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    if not raw_root:
        pytest.skip('Explicit retained public root; no network/source discovery')
    root = Path(raw_root).resolve()
    path = root/f'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-{filing}.pdf'
    before = path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == expected_hash
    pages = extract_pages(path)
    opening = ''.join(''.join(pages[:12]).split())
    assert '600519' in opening
    # This is a present-day raw-original research observation, not backdated acquisition/PIT.
    observed_at = datetime.now(timezone.utc)
    publication = '2026-04-17' if period.endswith('12-31') else '2026-08-15'
    source = adapter.RetainedAnnualSource('600519', period, path.relative_to(root).as_posix(),
        expected_hash, f'https://static.cninfo.com.cn/finalpage/{publication}/{filing}.PDF',
        observed_at.isoformat())
    scope = _source_financial_funding_scope({'page_texts': pages}, source)
    context = scope['research_context']
    assert context['status'] == 'SOURCE_BOUND_RESEARCH_OBSERVATIONS'
    assert context['period_label'] == period and context['symbol'] == '600519'
    assert len(context['observations']) == 4
    ids = {row['observation_id'] for row in context['observations']}
    ratio, = context['derivations']
    with localcontext() as dc:
        dc.prec = 48
        assert Decimal(ratio['value']) == Decimal(numerator)/Decimal(denominator)
    assert set(ratio['input_observation_ids']) <= ids
    for row in context['observations']:
        assert row['source_binding']['sha256'] == expected_hash
        assert row['period_label'] == period
        assert row['excerpt'] in pages[row['page']-1]
        assert row['financial_fact_admitted'] is False
    if period.endswith('06-30'):
        with pytest.raises(ValueError, match='annual period'):
            adapter.extract_retained_annual(root, source, evaluation_at=observed_at,
                cache_dir=root/'.tmp/H1_NOT_AN_ANNUAL_INPUT')
    assert path.read_bytes() == before


@pytest.mark.parametrize('symbol,expected_hash', [
    ('600519', 'e6dbb6a2f9080cf7a6cda9359540fe0d4b80ac7cdb113fa8f06648574137d9ce'),
    ('600887', '28f641afd580e9dea2c01abfc9af105e47974cbc92aab0500e799b9d9cfccdaa'),
])
def test_real_registered_income_adoption_preserves_identity_and_reads_fresh_funding_scope(symbol, expected_hash):
    import json
    import os
    from pathlib import Path
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import verify_enrichment_adoption

    raw_root = os.environ.get('VALUE_ENRICHMENT_REAL_ROOT')
    if not raw_root:
        pytest.skip('Explicit retained public root; no network/private/registration discovery')
    root = Path(raw_root).resolve()
    relative = ('runtime/retained-income-research-adoption/a26132256225470c97eec792b250fb71/'
                + symbol + '/' + symbol + '.json')
    path = root/relative
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    saved = json.loads(path.read_bytes())
    assert 'source_financial_funding_scope' not in saved  # Actual historical envelope.
    export = root/'runtime/retained-income-financial-input/9c9756f601f94001bcaa5d60a8d269cc/adapted/financial-export.json'
    export_hash = '2a6c5022d33d4835660160d8644053ca579a2fabef5ff88974ca3dc8dacff871'
    assert hashlib.sha256(export.read_bytes()).hexdigest() == export_hash
    result = verify_enrichment_adoption(root=root, result_binding=dict(path=relative, sha256=expected_hash),
        financial_export_path=export, financial_export_sha256=export_hash,
        evaluation_at=datetime.fromisoformat(saved['evaluation_at']))
    assert result['status'] == 'VERIFIED_FACT_ADOPTION'
    assert result['research_inputs_updated'] is True
    assert result['adopted_fact_ids'] == [p['data_point_id'] for p in saved['adopted_points']]
    assert result['adopted_fact_count'] == 2
    assert not result['complete_debt_verified']
    diagnostic = result['source_financial_funding_scope']
    assert diagnostic['symbol'] == symbol and diagnostic['period_label'] == '2025-12-31'
    assert diagnostic['source_binding']['sha256'] == saved['source_extraction']['identity']['source']['sha256']
    assert diagnostic['financial_fact_admitted'] is False
    if symbol == '600519':
        assert 'financial_deposits_and_interbank' in diagnostic['required_fields']
        observed = [r for r in diagnostic['observations'] if r['field_name'] == 'financial_deposits_and_interbank']
        assert len(observed) == 1 and Decimal(observed[0]['value']) == Decimal('18038383776.30')
        assert observed[0]['page'] == 58
        context = diagnostic['research_context']
        assert context['status'] == 'SOURCE_BOUND_RESEARCH_OBSERVATIONS'
        by_field = {row['field_name']: row for row in context['observations']}
        assert by_field['controlling_group_deposits']['value'] == '8330698318.34'
        assert by_field['consolidated_cash_and_equivalents']['value'] == '126425609447.72'
        assert by_field['issuer_parent_cash_and_equivalents']['value'] == '84730758118.65'
        ratio, = context['derivations']
        with localcontext() as dc:
            dc.prec = 48
            assert Decimal(ratio['value']) == Decimal('8330698318.34') / Decimal('18038383776.30')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    assert hashlib.sha256(export.read_bytes()).hexdigest() == export_hash


def test_isolated_complete_scope_reuses_assurance_and_scores_without_mutation(tmp_path, source):
    points, rows = _complete_points(tmp_path, source)
    original = deepcopy(points)
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
                                     cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert result['before']['total_score'] is None
    assert isinstance(result['after']['total_score'], Decimal)
    assert len(result['adopted_debt_fact_ids']) == 1
    assert result['adopted_debt_fact_ids'][0].startswith('interest_bearing_debt:scope:')
    assert result['adopted_points'][0]['metadata']['supersedes_id'] == 'interest_bearing_debt'
    assert datetime.fromisoformat(result['adopted_points'][0]['available_at']) <= NOW
    assert result['adopted_points'][0]['metadata']['derivation_rule_pit_status'] == 'NOT_ADMITTED'
    assert result['adopted_points'][0]['metadata']['complete_debt_verified'] is True
    assert points == original
    forged = deepcopy(points)
    for p in forged:
        if p['data_point_id'] == 'secondary-short_term_borrowings':
            p['sha256'] = 'f' * 64
    denied_backing = enrich_retained_company(tmp_path, source, forged, evaluation_at=NOW,
                                            cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert denied_backing['debt_scope']['complete_debt_verified'] is False
    assert any('INDEPENDENT_BACKING_BYTES_UNVERIFIED' in i for i in denied_backing['debt_scope']['issues'])
    unavailable = deepcopy(points)
    for p in unavailable:
        if p['data_point_id'] == 'secondary-short_term_borrowings':
            p['available_at'] = '2027-01-01T00:00:00+00:00'
    denied_future = enrich_retained_company(tmp_path, source, unavailable, evaluation_at=NOW,
                                           cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert denied_future['debt_scope']['complete_debt_verified'] is False
    assert any('INDEPENDENT_FACT_NOT_RETAINED' in i for i in denied_future['debt_scope']['issues'])
    pending = deepcopy(points)
    for p in pending:
        if p['data_point_id'] == 'secondary-short_term_borrowings':
            p['validation_status'] = 'pending'
    denied_pending = enrich_retained_company(tmp_path, source, pending, evaluation_at=NOW,
                                            cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert denied_pending['debt_scope']['complete_debt_verified'] is False
    assert any('INDEPENDENT_FACT_UNVERIFIED' in i for i in denied_pending['debt_scope']['issues'])
    rows[0]['metadata']['official_evidence']['excerpt'] = 'invented 10'
    denied = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
                                     cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert denied['after']['total_score'] is None
    assert any('ORIGINAL_BINDING_MISMATCH' in i for i in denied['debt_scope']['issues'])


def test_old_derived_debt_cannot_survive_failed_current_revalidation(tmp_path, source):
    from datetime import timedelta
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment
    points, rows = _complete_points(tmp_path, source)
    first = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/stale-debt', components=rows)
    later = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW+timedelta(days=1),
        cache_dir=tmp_path / '.tmp/stale-debt', components=rows)
    assert first['adopted_points'] == later['adopted_points']
    accumulated = points + deepcopy(first['adopted_points'])
    for point in accumulated:
        if point['data_point_id'] == 'secondary-short_term_borrowings':
            point['validation_status'] = 'pending'
    rejected = enrich_retained_company(tmp_path, source, accumulated, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/stale-debt', components=rows)
    assert rejected['debt_scope']['status'] == 'DATA_GAP'
    assert rejected['after']['total_score'] is None
    assert rejected['adopted_points'] == []
    active, _ = consume_retained_enrichment(tmp_path, accumulated, [], evaluation_at=NOW)
    assert not any(':scope:' in point['data_point_id'] for point in active)
    assert len(accumulated) > len(active)  # The caller's original archive was not mutated.


def test_balance_candidates_have_scope_period_and_do_not_fill_blank_debt():
    pages = ['\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n2025\u5e7412\u670831\u65e5 2024\u5e7412\u670831\u65e5\n'
             '\u5355\u4f4d\uff1a\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'
             '\u77ed\u671f\u501f\u6b3e \u4e03\uff0832\uff09 1,234.50 1,100.00\n'
             '\u5e94\u4ed8\u503a\u5238\n\u957f\u671f\u501f\u6b3e 23.00\n',
             '\u79df\u8d41\u8d1f\u503a 40.00 20.00\n\u8d1f\u503a\u548c\u6240\u6709\u8005\u6743\u76ca\u603b\u8ba1 2000.00 1500.00',
             '\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868\n\u77ed\u671f\u501f\u6b3e 99.00 88.00']
    result = adapter.extract_debt_balance_candidates(pages, '2025-12-31')
    assert [(r['field_name'], r['value']) for r in result] == [
        ('short_term_borrowings', '1234.50'), ('lease_liabilities_noncurrent', '40.00')]
    assert result[1]['unit_evidence_page'] == 1
    assert all(r['statement_scope'] == 'consolidated' for r in result)
    assert adapter.extract_debt_balance_candidates(pages, '2026-12-31') == []
    restated = [p.replace('\u5355\u4f4d', '(\u7ecf\u91cd\u8ff0)\n\u5355\u4f4d') for p in pages]
    assert len(adapter.extract_debt_balance_candidates(restated, '2025-12-31')) == 2


def test_scope_flag_without_retained_independent_fact_cannot_score(tmp_path, source):
    rows = components()
    for row in rows:
        row['metadata']['official_evidence']['sha256'] = source.sha256
    result = enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
                                     cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert result['debt_scope']['complete_debt_verified'] is False
    assert any('INDEPENDENT_FACT_NOT_RETAINED' in i for i in result['debt_scope']['issues'])


def test_lawful_consumption_reaches_priority_and_rechecks_source(tmp_path, source, monkeypatch):
    from dataclasses import asdict, replace
    import json
    from test_value_research_priority_v2 import _inputs
    from value_investment_agent.application.research.value_research_priority_v2 import build_value_research_priority_v2

    source = replace(source, symbol='600001')
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: [
        '\u80a1\u7968\u4ee3\u7801: 600001; 2025\u5e74\u5e74\u5ea6\u62a5\u544a TEST_ONLY amount 10'])
    points, _ = _complete_points(tmp_path, source)
    for point in points:
        point['symbol'] = source.symbol
    args = _inputs(tmp_path)
    supplement = tmp_path / 'runtime/consumption.json'
    payload = {'points': [], 'annual_points': points, 'value_enrichment_sources': [asdict(source)]}
    def build():
        supplement.write_text(json.dumps(payload), encoding='utf-8')
        return build_value_research_priority_v2(**dict(args, financial_export_path=supplement,
            financial_export_sha256=hashlib.sha256(supplement.read_bytes()).hexdigest()))
    result = build()
    assert result['deep_research_priority'], result['retained_enrichment_adoption'][0]['debt_scope']['issues']
    assert result['deep_research_priority'][0]['symbol'] == source.symbol
    assert result['deep_research_priority'][0]['quality_score'] is not None
    assert result['retained_enrichment_adoption'][0]['adopted_debt_fact_ids'][0].startswith('interest_bearing_debt:scope:')
    assert result['new_verification_or_approval_count'] == 0
    assert points == payload['annual_points']
    for point in points:
        if point['data_point_id'] == 'secondary-short_term_borrowings':
            point['validation_status'] = 'pending'
    denied = build()
    assert not denied['deep_research_priority']
    assert not denied['retained_enrichment_adoption'][0]['adopted_debt_fact_ids']
    (tmp_path / 'annual.pdf').write_bytes(b'changed original')
    with pytest.raises(ValueError, match='hash mismatch'):
        build()


@pytest.mark.parametrize('future', [False, True])
def test_completed_checkpoint_feedback_is_consumed_only_after_actual_completion(tmp_path, source, monkeypatch, future):
    from dataclasses import replace
    import json
    from datetime import timedelta
    from test_value_research_priority_v2 import _inputs
    from value_investment_agent.application.research.value_research_priority_v2 import build_value_research_priority_v2
    from value_investment_agent.infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
    source = replace(source, symbol='600001')
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: [
        '\u80a1\u7968\u4ee3\u7801: 600001; 2025\u5e74\u5e74\u5ea6\u62a5\u544a TEST_ONLY amount 10'])
    points, _ = _complete_points(tmp_path, source)
    for point in points:
        point['symbol'] = source.symbol
    args = _inputs(tmp_path)
    path = tmp_path / 'runtime/reviewed-financial.json'
    path.write_text(json.dumps({'points': [], 'annual_points': points}), encoding='utf-8')
    args.update(financial_export_path=path, financial_export_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    before = build_value_research_priority_v2(**args)
    assert before['deep_research_priority'] == []
    cutoff = datetime.fromisoformat(before['evaluation_at'])
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=cutoff-timedelta(minutes=2),
        cache_dir=tmp_path / '.tmp/test-only-feedback')
    result_path = tmp_path / 'runtime/test-only-result.json'
    result_path.write_text(json.dumps(result, default=str), encoding='utf-8')
    binding = lambda p: {'path': p.relative_to(tmp_path).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    attempt = tmp_path / 'runtime/test-only-attempt.json'
    attempt.write_text(json.dumps({'state': 'QUALITY_EVALUATED', 'result_binding': binding(result_path)}), encoding='utf-8')
    progress = ValueEnrichmentProgress(tmp_path)
    with progress.locked():
        progress.save({'key': 'f'*64, 'attempt': 1, 'execution_binding': binding(attempt),
            'completed_at': (cutoff + timedelta(minutes=1) if future else cutoff-timedelta(minutes=1)).isoformat()})
    after = build_value_research_priority_v2(**args)
    assert bool(after['deep_research_priority']) is (not future)
    if not future:
        assert after['retained_enrichment_adoption'][0]['adopted_debt_fact_ids']
        assert after['new_verification_or_approval_count'] == 0
        source_path = tmp_path / source.path
        source_path.write_bytes(b'changed TEST_ONLY original')
        with pytest.raises(ValueError, match='hash mismatch'):
            build_value_research_priority_v2(**args)


@pytest.fixture
def balance_inputs(tmp_path, source, monkeypatch):
    pages = ['\u80a1\u7968\u4ee3\u7801: 600887; 2025\u5e74\u5e74\u5ea6\u62a5\u544a',
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n2025\u5e7412\u670831\u65e5 2024\u5e7412\u670831\u65e5\n'
        '\u5355\u4f4d\uff1a\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'
        '\u8d44\u4ea7\u603b\u8ba1 1,000.00 900.00\n\u8d1f\u503a\u5408\u8ba1 200.00 180.00']
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    rows = []
    for field, value in [('total_assets', '1000'), ('total_liabilities', '200')]:
        rows.append(dict(symbol=source.symbol, field_name=field, value=value, unit='CNY',
            data_point_id=field, source_id='official', source_url=source.source_url,
            sha256=source.sha256, period_label=source.period, validation_status='verified',
            created_at=source.available_at, fetched_at=source.available_at,
            metadata=dict(automatic_cross_source_verification=True,
                          statement_scope='consolidated', currency='CNY')))
    return source, rows, pages


def test_official_balance_derivation_consumption_is_stable_and_not_complete_debt(tmp_path, balance_inputs):
    from dataclasses import asdict
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment
    source, points, _ = balance_inputs
    original = deepcopy(points)
    first, reports = consume_retained_enrichment(tmp_path, points, [asdict(source)], evaluation_at=NOW)
    ratio = first[-1]
    assert ratio['field_name'] == 'debt_ratio' and Decimal(ratio['value']) == 20
    assert reports[0]['adopted_fact_ids'] == [ratio['data_point_id']]
    assert not reports[0]['debt_scope']['complete_debt_verified']
    assert reports[0]['adopted_debt_fact_ids'] == []
    second, _ = consume_retained_enrichment(tmp_path, first, [asdict(source)], evaluation_at=NOW)
    assert first == second and points == original


@pytest.mark.parametrize('change', ['pending', 'quarantine', 'parent', 'unit', 'source', 'amount', 'future', 'duplicate'])
def test_balance_derivation_rejects_invalid_input_assurance_or_binding(tmp_path, balance_inputs, change):
    source, points, _ = balance_inputs
    if change == 'pending':
        points[0]['validation_status'] = 'pending'
    elif change == 'quarantine':
        points[0]['metadata']['evidence_quarantine'] = True
    elif change == 'parent':
        points[0]['metadata']['statement_scope'] = 'parent'
    elif change == 'unit':
        points[0]['unit'] = 'CNY 100M'
    elif change == 'source':
        points[0]['sha256'] = 'b' * 64
    elif change == 'amount':
        points[0]['value'] = '1001'
    elif change == 'future':
        points[0]['available_at'] = '2027-01-01T00:00:00+00:00'
    else:
        points.append(dict(deepcopy(points[0]), data_point_id='different-input-version'))
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/balance')
    assert result['balance_ratio_adoption']['status'] == 'REJECTED_WITH_REASON'
    assert not result['adopted_points']


def test_balance_period_and_blank_unit_cannot_be_inferred(tmp_path, balance_inputs):
    source, points, pages = balance_inputs
    pages[1] = pages[1].replace('2025', '2026')
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/wrong-period')
    assert not result['adopted_points']


def test_source_derived_fact_registers_typed_research_and_revalidates_before_writing(tmp_path, income_inputs):
    from datetime import date
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import register_enriched_research
    from value_investment_agent.research_case import ResearchCase
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.research_artifacts import parse_stored_artifact_payload
    from value_investment_agent.research_input import facts_from_payload
    from value_investment_agent.valuation_models.fcff import FinancialFacts
    source, points, _ = income_inputs
    points[:] = [p for p in points if p['period_label'] != '2024-12-31']
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/registration')
    case = ResearchCase(symbol=source.symbol, name='TEST_ONLY', as_of=NOW.date(),
        generated_at=NOW, run_id='test', research_version='test-v1', industry='TEST_ONLY',
        investment_path='UNASSESSED', thesis='TEST_ONLY', return_driver='UNASSESSED',
        mispricing_hypothesis='UNASSESSED', financial_summary={}, positives=[], counter_evidence=[],
        thesis_breakers=[], next_events=[], evidence_status='PARTIAL', valuation_status='NOT_ASSESSED',
        research_status='DATA_CHECK', blockers=['MISSING_ECONOMIC_INPUTS'], evidence_refs=[],
        quote_date=None, financial_period=date(2025, 12, 31),
        missing_date_reasons={'quote_date': 'No quote used by this test'})
    facts = FinancialFacts(source.symbol, NOW.date(), False, [], ['MISSING_ECONOMIC_INPUTS'])
    repository = InMemoryResearchArtifactRepository()
    args = dict(root=tmp_path, points=points, repository=repository, case=case, facts=facts, run_id='test')
    registered = register_enriched_research(result, **args)
    stored = repository.load_by_id(registered['financial_facts_artifact_id'])
    consumed = facts_from_payload(parse_stored_artifact_payload(stored))
    assert consumed.operating_inputs['debt_ratio'] == Decimal(20)
    assert not consumed.verified and consumed.scenario_inputs is None
    assert not registered['formal_eligibility']
    case_payload = parse_stored_artifact_payload(repository.load_by_id(registered['research_case_artifact_id']))
    assert case_payload['financial_summary']['value_enrichment']['financial_facts']['sha256'] == stored.envelope.payload_sha256
    observations = case_payload['financial_summary']['value_enrichment']['sourced_arithmetic_observations']
    assert len(observations) == 2 and all(p['validation_status'] == 'pending' for p in observations)
    assert 'revenue_yoy' not in consumed.operating_inputs
    assert register_enriched_research(result, **args) == registered
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import verify_enrichment_adoption
    import json
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    export = runtime / 'financial.json'
    export.write_text(json.dumps({'points': points}), encoding='utf-8')
    result_path = runtime / 'result.json'
    saved = dict(result, research_registration=registered)
    def verify_saved():
        result_path.write_text(json.dumps(saved, default=str), encoding='utf-8')
        return verify_enrichment_adoption(root=tmp_path,
            result_binding={'path': 'runtime/result.json', 'sha256': hashlib.sha256(result_path.read_bytes()).hexdigest()},
            financial_export_path=export, financial_export_sha256=hashlib.sha256(export.read_bytes()).hexdigest(),
            evaluation_at=NOW)
    summary = verify_saved()
    assert summary['status'] == 'VERIFIED_FACT_ADOPTION' and summary['adopted_fact_count'] == 1
    assert summary['research_inputs_updated'] and summary['new_fact_approvals'] == 0
    assert summary['sourced_arithmetic_observation_count'] == 2
    assert not summary['complete_debt_verified'] and not summary['formal_eligibility']
    saved['research_registration']['artifacts'][0]['envelope']['canonical_payload'] = '{"forged":true}'
    with pytest.raises(ValueError, match='hash does not match'):
        verify_saved()
    # The mutation above is to the returned transport snapshot, not repository state.
    saved['research_registration'] = register_enriched_research(result, **args)
    saved['adopted_points'] = deepcopy(result['adopted_points'])
    saved['adopted_points'][0]['value'] = '0'
    with pytest.raises(ValueError, match='revalidated source facts'):
        verify_saved()
    forged = deepcopy(result)
    forged['adopted_points'][0]['value'] = '0'
    with pytest.raises(ValueError, match='revalidated source facts'):
        register_enriched_research(forged, **args)
    (tmp_path / source.path).write_bytes(b'changed original')
    with pytest.raises(ValueError, match='hash mismatch'):
        register_enriched_research(result, **args)
    assert len(repository.list_versions('security', source.symbol, 'financial_facts')) == 1


def test_ratio_feedback_reranks_research_queue_without_economic_admission(tmp_path, balance_inputs, monkeypatch):
    from dataclasses import asdict, replace
    import json
    from test_value_research_priority_v2 import _inputs
    from value_investment_agent.application.research.value_research_priority_v2 import build_value_research_priority_v2
    source, points, pages = balance_inputs
    source = replace(source, symbol='600004')
    pages[0] = pages[0].replace('600887', source.symbol)
    for point in points:
        point['symbol'] = source.symbol
    args = _inputs(tmp_path, pending=True)
    payload = json.loads(args['financial_export_path'].read_bytes())
    payload['annual_points'].extend(points)
    supplement = tmp_path / 'runtime/balance-supplement.json'
    def build():
        supplement.write_text(json.dumps(payload), encoding='utf-8')
        return build_value_research_priority_v2(**dict(args, financial_export_path=supplement,
            financial_export_sha256=hashlib.sha256(supplement.read_bytes()).hexdigest()))
    before = build()
    payload['value_enrichment_sources'] = [asdict(source)]
    after = build()
    assert before['evidence_enrichment_work_queue'][0]['symbol'] != source.symbol
    assert after['evidence_enrichment_work_queue'][0]['symbol'] == source.symbol
    assert 'debt_ratio' in after['evidence_enrichment_work_queue'][0]['evidence_completeness']['accepted_fields']
    assert not after['deep_research_priority']
    assert after['new_verification_or_approval_count'] == 0


@pytest.fixture
def income_inputs(balance_inputs):
    source, points, pages = balance_inputs
    pages.extend(['\u5408\u5e76\u5229\u6da6\u8868\n2025\u5e74\u5ea6 2024\u5e74\u5ea6\n'
        '\u5355\u4f4d\uff1a\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'
        '\u8425\u4e1a\u603b\u6536\u5165 999.00 888.00\n\u8425\u4e1a\u6536\u5165 44 120.00 100.00',
        '\u4e94\u3001\u51c0\u5229\u6da6 30.00 20.00\n'
        '\u5f52\u5c5e\u4e8e\u6bcd\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da6\n'
        '\uff08\u51c0\n\u4e8f\u635f\u4ee5\u201c-\u201d\u53f7\u586b\u5217\uff09\n24.00 20.00'])
    for field, current, prior in [('revenue', '120', '100'), ('net_income', '24', '20')]:
        for period, value in [(source.period, current), ('2024-12-31', prior)]:
            points.append(dict(deepcopy(points[0]), field_name=field, value=value,
                data_point_id=field + ':' + period, period_label=period))
    return source, points, pages


def test_growth_derives_both_fields_with_admitted_denominators_and_reuses(tmp_path, income_inputs):
    from dataclasses import asdict
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment
    source, points, _ = income_inputs
    first, reports = consume_retained_enrichment(tmp_path, points, [asdict(source)], evaluation_at=NOW)
    derived = [p for p in first if p['field_name'].endswith('_yoy')]
    assert {p['field_name'] for p in derived} == {'revenue_yoy', 'net_income_yoy'}
    assert all(Decimal(p['value']) == 20 and p['validation_status'] == 'verified' for p in derived)
    second, _ = consume_retained_enrichment(tmp_path, first, [asdict(source)], evaluation_at=NOW)
    assert first == second
    assert all(row['status'] == 'FACT_ADMITTED' for row in reports[0]['income_growth_adoption'])


@pytest.mark.parametrize('change', ['prior_missing', 'prior_pending', 'prior_parent', 'prior_future',
    'duplicate', 'current_mismatch', 'nonpositive'])
def test_growth_keeps_unadmitted_inputs_out_of_quality(tmp_path, income_inputs, change):
    source, points, pages = income_inputs
    prior = next(p for p in points if p['data_point_id'] == 'revenue:2024-12-31')
    if change == 'prior_missing':
        points.remove(prior)
    elif change == 'prior_pending':
        prior['validation_status'] = 'pending'
    elif change == 'prior_parent':
        prior['metadata']['statement_scope'] = 'parent'
    elif change == 'prior_future':
        prior['available_at'] = '2027-01-01T00:00:00+00:00'
    elif change == 'duplicate':
        points.append(dict(prior, data_point_id='duplicate'))
    elif change == 'current_mismatch':
        next(p for p in points if p['data_point_id'] == 'revenue:2025-12-31')['value'] = '121'
    else:
        pages[2] = pages[2].replace('120.00 100.00', '120.00 0.00')
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/income')
    assert 'revenue_yoy' not in {p['field_name'] for p in result['adopted_points']}
    if change != 'nonpositive':
        observation = result['sourced_arithmetic_points'][0]
        assert observation['validation_status'] == 'pending'
        assert not observation['metadata']['automatic_cross_source_verification']
        assert Decimal(observation['value']) == 20


@pytest.mark.parametrize('change', ['unit', 'columns', 'restatement', 'parent', 'three_columns'])
def test_income_parser_rejects_unproven_table_layout(income_inputs, change):
    _, _, pages = income_inputs
    if change == 'unit':
        pages[2] = pages[2].replace('\u5355\u4f4d\uff1a\u5143', '')
    elif change == 'columns':
        pages[2] = pages[2].replace('2025\u5e74\u5ea6 2024\u5e74\u5ea6', '2024\u5e74\u5ea6 2025\u5e74\u5ea6')
    elif change == 'restatement':
        pages[2] += '\n\u8c03\u6574\u540e'
    elif change == 'parent':
        pages[2] = pages[2].replace('\u5408\u5e76\u5229\u6da6\u8868', '\u6bcd\u516c\u53f8\u5229\u6da6\u8868')
    else:
        pages[2] = pages[2].replace('120.00 100.00', '120.00 100.00 90.00')
    assert not [p for p in adapter.extract_income_comparatives(pages, '2025-12-31') if p['field_name'] == 'revenue']
