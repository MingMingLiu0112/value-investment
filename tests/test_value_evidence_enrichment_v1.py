from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
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


def test_isolated_complete_scope_reuses_assurance_and_scores_without_mutation(tmp_path, source):
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
    original = deepcopy(points)
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
                                     cache_dir=tmp_path / '.tmp/cache', components=rows)
    assert result['before']['total_score'] is None
    assert isinstance(result['after']['total_score'], Decimal)
    assert result['adopted_debt_fact_ids'] == ['interest_bearing_debt']
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
