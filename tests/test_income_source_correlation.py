from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.research import income_source_correlation as correlation
from value_investment_agent.infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource


NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    source = RetainedAnnualSource('600887', '2025-12-31', 'annual.pdf', 'a' * 64,
        'https://static.cninfo.com.cn/test.pdf', '2026-09-01T00:00:00+00:00')
    reports = {year + '1231': dict(rCurrency='CNY', rType='\u5408\u5e76\u671f\u672b',
        publish_date='20260420', data=[dict(item_field='BIZINCO', item_value=revenue, item_source='lrb'),
            dict(item_field='PARENETP', item_value=profit, item_source='lrb')])
        for year, revenue, profit in [('2025', '200.00', '30.00'), ('2024', '180.00', '25.00')]}
    payload = dict(result=dict(data=dict(report_list=reports)))
    path = tmp_path / 'income.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    descriptor = dict(path='income.json', sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        acquired_at='2026-10-20T00:00:00+00:00',
        source_url='https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022?paperCode=sh600887&source=lrb&type=0')
    receipt = dict(url=descriptor['source_url'], path=descriptor['path'], sha256=descriptor['sha256'],
                   acquired_at=descriptor['acquired_at'], bytes=path.stat().st_size, action='no_order')
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    descriptor['receipt'] = dict(path='receipt.json', sha256=hashlib.sha256((tmp_path / 'receipt.json').read_bytes()).hexdigest())
    packet = dict(income_comparatives=[dict(field_name=field, value=current, prior_value=prior,
        prior_period_label='2024-12-31', page=2, excerpt='TEST_ONLY official income comparative')
        for field, current, prior in [('revenue', '200.00', '180.00'), ('net_income', '30.00', '25.00')]])
    monkeypatch.setattr(correlation, 'extract_retained_annual', lambda *a, **k: packet)
    return tmp_path, source, descriptor, payload


def test_exact_amounts_and_replay_preserve_nonapproval_and_acquisition_clock(fixture):
    root, source, descriptor, _ = fixture
    points = correlation.correlate_income_inputs(root, source, descriptor, evaluation_at=NOW)
    assert len(points) == 4
    assert {p['period_label'] for p in points} == {'2024-12-31', '2025-12-31'}
    assert all(p['available_at'] == descriptor['acquired_at'] for p in points)
    assert all(p['metadata']['economic_approval'] is False for p in points)
    correlation.reverify_income_inputs(root, source, points, evaluation_at=NOW)
    assert points == correlation.correlate_income_inputs(root, source, descriptor, evaluation_at=NOW)


@pytest.mark.parametrize('mutation', [
    lambda r: r.update(rCurrency='USD'),
    lambda r: r.update(rType='parent'),
    lambda r: r.update(publish_date='20271021'),
    lambda r: r['data'][0].update(item_field='BIZTOTINCO'),
    lambda r: r['data'][1].update(item_field='NETPROFIT'),
    lambda r: r['data'][0].update(item_value='200.01'),
    lambda r: r['data'][0].update(item_value=None),
    lambda r: r['data'][0].update(item_value='NaN'),
    lambda r: r['data'].append(deepcopy(r['data'][0])),
])
def test_structured_scope_field_amount_and_ambiguity_rejected(fixture, mutation):
    root, source, descriptor, payload = fixture
    mutation(payload['result']['data']['report_list']['20251231'])
    (root / 'income.json').write_text(json.dumps(payload), encoding='utf-8')
    descriptor['sha256'] = hashlib.sha256((root / 'income.json').read_bytes()).hexdigest()
    receipt = json.loads((root / 'receipt.json').read_bytes())
    receipt.update(sha256=descriptor['sha256'], bytes=(root / 'income.json').stat().st_size)
    (root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    descriptor['receipt']['sha256'] = hashlib.sha256((root / 'receipt.json').read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        correlation.correlate_income_inputs(root, source, descriptor, evaluation_at=NOW)


@pytest.mark.parametrize('key,value', [
    ('sha256', 'b' * 64), ('acquired_at', '2027-01-01T00:00:00+00:00'),
    ('acquired_at', '2026-10-01T00:00:00'), ('path', '../outside.json'),
    ('acquired_at', '2026-04-21T00:00:00+00:00'),
    ('source_url', 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022?paperCode=sh600519&source=lrb&type=0'),
    ('source_url', 'https://evil.example/income.json'),
])
def test_descriptor_guards(fixture, key, value):
    root, source, descriptor, _ = fixture
    descriptor[key] = value
    with pytest.raises(ValueError):
        correlation.correlate_income_inputs(root, source, descriptor, evaluation_at=NOW)


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(value='999'),
    lambda p: p.update(period_label='2023-12-31'),
    lambda p: p['metadata'].update(income_source_version='forged'),
    lambda p: p['metadata'].pop('income_secondary'),
])
def test_rebound_point_cannot_reuse_saved_verification(fixture, mutation):
    root, source, descriptor, _ = fixture
    points = correlation.correlate_income_inputs(root, source, descriptor, evaluation_at=NOW)
    mutation(points[0])
    with pytest.raises((ValueError, TypeError)):
        correlation.reverify_income_inputs(root, source, points, evaluation_at=NOW)


def test_original_rows_are_not_reclassified(fixture):
    root, source, _, _ = fixture
    original = [dict(data_point_id='existing', value='123', metadata={})]
    correlation.reverify_income_inputs(root, source, original, evaluation_at=NOW)
    assert original == [dict(data_point_id='existing', value='123', metadata={})]


def test_acquisition_receipt_tamper_is_not_just_a_descriptor_change(fixture):
    root, source, descriptor, _ = fixture
    (root / 'receipt.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='receipt hash mismatch'):
        correlation.correlate_income_inputs(root, source, descriptor, evaluation_at=NOW)
