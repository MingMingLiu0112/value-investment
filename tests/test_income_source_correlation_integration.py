"""TEST_ONLY retained originals exercise real correlation and growth adoption."""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from test_value_evidence_enrichment_v1 import source, balance_inputs, income_inputs, NOW
from value_investment_agent.application.research.income_source_correlation import correlate_income_inputs
from value_investment_agent.application.research.value_evidence_enrichment_v1 import (
    enrich_retained_company, consume_retained_enrichment,
)


@pytest.fixture
def correlated_income(tmp_path, income_inputs):
    official, points, _ = income_inputs
    # Reuse the real comparative parser over the existing mocked PDF pages.
    # The baseline has admitted current amounts but no prior denominators.
    baseline = [deepcopy(point) for point in points if point['period_label'] == official.period]
    reports = {period: dict(rCurrency='CNY', rType='\u5408\u5e76\u671f\u672b',
        publish_date='20260420', data=[
            dict(item_field='BIZINCO', item_value=revenue, item_source='lrb'),
            dict(item_field='PARENETP', item_value=profit, item_source='lrb')])
        for period, revenue, profit in [('20251231', '120.00', '24.00'), ('20241231', '100.00', '20.00')]}
    path = tmp_path / 'runtime/TEST_ONLY-income-secondary.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result=dict(data=dict(report_list=reports)))), encoding='utf-8')
    descriptor = dict(path=path.relative_to(tmp_path).as_posix(),
        sha256=sha256(path.read_bytes()).hexdigest(), acquired_at=(NOW - timedelta(hours=1)).isoformat(),
        source_url='https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022?paperCode=sh600887&source=lrb&type=0')
    receipt_path = path.with_name('TEST_ONLY-income-acquisition-receipt.json')
    receipt = dict(url=descriptor['source_url'], path=descriptor['path'], sha256=descriptor['sha256'],
        acquired_at=descriptor['acquired_at'], bytes=len(path.read_bytes()), action='no_order')
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    descriptor['receipt'] = dict(path=receipt_path.relative_to(tmp_path).as_posix(),
        sha256=sha256(receipt_path.read_bytes()).hexdigest())
    correlated = correlate_income_inputs(tmp_path, official, descriptor, evaluation_at=NOW)
    assert len(correlated) == 4
    return official, baseline, correlated, descriptor, path


def enrich(root, official, points):
    return enrich_retained_company(root, official, points, evaluation_at=NOW,
        cache_dir=root / '.tmp/value-enrichment-extraction')


@pytest.mark.parametrize('input_mode', ['correlated_prior_only', 'correlated_both_periods'])
def test_source_correlation_closes_prior_inputs_and_admits_growth(tmp_path, correlated_income, input_mode):
    official, baseline, correlated, descriptor, _ = correlated_income
    before = enrich(tmp_path, official, baseline)
    assert {point['field_name'] for point in before['adopted_points']} == {'debt_ratio'}
    assert {point['field_name'] for point in before['sourced_arithmetic_points']} == {'revenue_yoy', 'net_income_yoy'}
    assert all(point['validation_status'] == 'pending' for point in before['sourced_arithmetic_points'])
    prior = [point for point in correlated if point['period_label'] == '2024-12-31']
    assert {(point['field_name'], Decimal(point['value'])) for point in prior} == {
        ('revenue', Decimal('100')), ('net_income', Decimal('20'))}
    if input_mode == 'correlated_prior_only':
        inputs = baseline + prior
    else:
        inputs = [point for point in baseline if point['field_name'] not in {'revenue', 'net_income'}] + correlated
    original = deepcopy(inputs)
    after = enrich(tmp_path, official, inputs)
    growth = [point for point in after['adopted_points'] if point['field_name'].endswith('_yoy')]
    assert {point['field_name'] for point in growth} == {'revenue_yoy', 'net_income_yoy'}
    assert all(Decimal(point['value']) == 20 and point['validation_status'] == 'verified' for point in growth)
    assert all(row['status'] == 'FACT_ADMITTED' for row in after['income_growth_adoption'])
    assert not after['sourced_arithmetic_points']
    for point in growth:
        field = point['field_name'].removesuffix('_yoy')
        denominator = next(row for row in prior if row['field_name'] == field)
        assert denominator['data_point_id'] in point['metadata']['input_fact_ids']
        assert point['available_at'] == descriptor['acquired_at']
        assert not point['human_reviewed']
    assert str(before['after']['coverage_ratio']) == '0.1111'
    assert str(after['after']['coverage_ratio']) == '0.3333'
    assert after['after']['total_score'] is None
    assert after['debt_scope']['complete_debt_verified'] is False
    assert after['formal_eligibility'] is False and after['action'] == 'no_order'
    assert all(point['metadata']['economic_approval'] is False
               and point['metadata']['historical_pit_admission'] == 'NOT_ADMITTED'
               and point['human_reviewed'] is False for point in correlated)
    assert inputs == original
    # Replaying the resulting retained facts uses both source checks and growth
    # derivation again; previously saved verification flags do not replace them.
    merged, reports = consume_retained_enrichment(tmp_path, inputs, [asdict(official)], evaluation_at=NOW)
    repeated, _ = consume_retained_enrichment(tmp_path, merged, [asdict(official)], evaluation_at=NOW)
    assert merged == repeated
    assert {point['data_point_id'] for point in growth} <= set(reports[0]['adopted_fact_ids'])


@pytest.mark.parametrize('tamper', ['official_original', 'secondary_original'])
def test_already_adopted_growth_rejects_changed_source_bytes_with_warm_cache(tmp_path, correlated_income, tamper):
    official, baseline, correlated, _, secondary_path = correlated_income
    inputs = baseline + [point for point in correlated if point['period_label'] == '2024-12-31']
    accepted = enrich(tmp_path, official, inputs)
    growth = [point for point in accepted['adopted_points'] if point['field_name'].endswith('_yoy')]
    assert len(growth) == 2
    assert str(accepted['after']['coverage_ratio']) == '0.3333'
    saved = deepcopy(inputs + accepted['adopted_points'])
    assert list((tmp_path / '.tmp/value-enrichment-extraction').glob('*.json'))
    path = tmp_path / official.path if tamper == 'official_original' else secondary_path
    # Whitespace alone preserves parsed values but breaks the adopted hash.
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        enrich(tmp_path, official, saved)
    with pytest.raises(ValueError, match='hash mismatch'):
        consume_retained_enrichment(tmp_path, saved, [asdict(official)], evaluation_at=NOW)
    assert all(point['validation_status'] == 'verified' for point in growth)
    assert accepted['formal_eligibility'] is False and accepted['action'] == 'no_order'
