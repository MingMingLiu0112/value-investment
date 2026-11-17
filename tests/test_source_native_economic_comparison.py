"""Opt-in real official inputs; isolated generated artifacts, no current admission."""
from copy import deepcopy
import json
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_source_native_economic_review_v1 import public_js2, snapshot
from value_investment_agent.application.product import source_native_economic_review_v1 as review
from value_investment_agent.application.research.source_native_operating_erosion_v1 import build_source_native_operating_erosion
from value_investment_agent.presentation.web_api.source_native_economic_routes import register_source_native_economic_routes


@pytest.fixture
def pair(public_js2):
    root, baseline, _ = public_js2
    name = 'src/value_investment_agent/domain/valuation/operating_realization_erosion_v1.py'
    target = root/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).resolve().parents[1]/name, target)
    generated = build_source_native_operating_erosion(root=root, candidate_binding=baseline,
        output_dir=root/'runtime/TEST_ONLY-official-comparison')
    return root, baseline, generated['candidate_binding']


def test_official_pair_replayed_without_registration_or_writes(pair):
    root, baseline, replacement = pair
    before = snapshot(root)
    result = review.build_source_native_economic_review(root=root, candidate_binding=baseline,
        replacement_candidate_binding=replacement)
    appendix = result['replacement_bear']
    assert appendix['status'] == 'VERIFIED_BOUND_RESEARCH_COMPARISON'
    assert appendix['baseline_candidate_binding'] == baseline
    assert appendix['replacement_candidate_binding'] == replacement
    assert appendix['base_bull_exactly_preserved'] is True
    assert appendix['price_admitted'] is appendix['research_admitted'] is appendix['formal_eligibility'] is False
    assert len(appendix['operating_rows']) == len(appendix['annual_cash_rows']) == 5
    assert snapshot(root) == before
    registry = root/'config/user-research-workflow-v1.json'
    registry.parent.mkdir(exist_ok=True)
    registry.write_text(json.dumps(dict(schema_version='user-research-workflow-v1',action='no_order',
        supplemental_review_candidates={'600519':baseline})),encoding='utf-8')
    mapping = {'600519':dict(baseline_candidate_binding=baseline,replacement_candidate_binding=replacement)}
    api = FastAPI()
    register_source_native_economic_routes(api, project=root, replacement_bindings=lambda:deepcopy(mapping))
    before = snapshot(root)
    response = TestClient(api).get('/api/v1/value-economic-review/600519')
    assert response.status_code == 200, response.text
    assert response.json()['replacement_bear'] == appendix
    assert snapshot(root) == before
    (root/'comparison-response.json').write_text(json.dumps(response.json(),ensure_ascii=False),encoding='utf-8')


@pytest.mark.parametrize('damage', ['base', 'bull', 'cash', 'history', 'model_basis', 'sources', 'model', 'evidence',
    'proxy_binding', 'proxy_revenue', 'proxy_volume', 'observed_past', 'observed_future', 'observed_invalid'])
def test_actual_native_positive_then_relationship_corruption_rejected(pair, monkeypatch, damage):
    """Instrument projection reads only, never replace the native verifier."""
    root, baseline, replacement = pair
    candidate = json.loads((root/replacement['path']).read_bytes())
    read = review._json
    def altered(root, ref):
        path, value = read(root, ref)
        value = deepcopy(value)
        if ref == replacement and damage == 'model': value['model_context']['profile_id'] = 'WRONG'
        if ref == candidate['source_package_binding']:
            if damage in ('base','bull'): value['facts']['scenario_inputs'][damage]['cost_of_equity'] = '0.9'
            elif damage == 'model_basis': value['facts']['operating_inputs']['ordinary_shares'] = '1'
            elif damage == 'sources': value['sources'] = value['sources'][1:]
        if ref == candidate['native_cash_ledger_binding']:
            if damage == 'cash': value['plan']['incremental_parent_cash_yield'] = '0.9'
            elif damage == 'history': value['history']['ttm']['cash_end'] = '1'
        if damage == 'evidence' and ref['path'].endswith('/operating-inputs.json'):
            value['operating_rows'][0]['revenue'] = '1'
        if ref['path'].endswith('/operating-inputs.json'):
            if damage == 'proxy_binding':
                value['mixed_proxy']['source_binding'] = dict(path='runtime/NOT_A_SOURCE.pdf',sha256='0'*64,page=999)
            elif damage == 'proxy_revenue': value['mixed_proxy']['revenue_yoy_pct'] = '-2.08'
            elif damage == 'proxy_volume': value['mixed_proxy']['volume_yoy_pct'] = '3.13'
            elif damage == 'observed_past': value['observed_at'] = '2020-01-01T00:00:00+00:00'
            elif damage == 'observed_future': value['observed_at'] = '2099-01-01T00:00:00+00:00'
            elif damage == 'observed_invalid': value['observed_at'] = '2026-02-30T00:00:00+00:00'
        return path, value
    monkeypatch.setattr(review, '_json', altered)
    with pytest.raises(ValueError):
        review.build_source_native_economic_review(root=root,candidate_binding=baseline,
            replacement_candidate_binding=replacement)
    if damage in ('proxy_binding','observed_past'):
        registry = root/'config/user-research-workflow-v1.json'
        registry.parent.mkdir(exist_ok=True)
        registry.write_text(json.dumps(dict(schema_version='user-research-workflow-v1',action='no_order',
            supplemental_review_candidates={'600519':baseline})),encoding='utf-8')
        api = FastAPI()
        register_source_native_economic_routes(api,project=root,replacement_bindings={
            '600519':dict(baseline_candidate_binding=baseline,replacement_candidate_binding=replacement)})
        response = TestClient(api).get('/api/v1/value-economic-review/600519')
        assert response.status_code == 409
        assert 'scenarios' not in response.json() and 'replacement_bear' not in response.json()


def test_equivalent_observation_timezone_is_same_instant(pair, monkeypatch):
    from datetime import datetime, timedelta, timezone
    root, baseline, replacement = pair
    read = review._json
    def zoned(root, ref):
        path, value = read(root, ref)
        if ref['path'].endswith('/operating-inputs.json'):
            value = deepcopy(value)
            value['observed_at'] = datetime.fromisoformat(value['observed_at']).astimezone(timezone(timedelta(hours=8))).isoformat()
        return path, value
    monkeypatch.setattr(review, '_json', zoned)
    result = review.build_source_native_economic_review(root=root,candidate_binding=baseline,
        replacement_candidate_binding=replacement)
    assert result['replacement_bear']['status'] == 'VERIFIED_BOUND_RESEARCH_COMPARISON'


@pytest.mark.parametrize('damage', ['original', 'replacement', 'evidence'])
def test_both_closures_rechecked_after_comparison(pair, monkeypatch, damage):
    root, baseline, replacement = pair
    helper = review._replacement_bear
    def drift(*args, **kwargs):
        result = helper(*args, **kwargs)
        ref = baseline if damage == 'original' else replacement if damage == 'replacement' else result['evidence_binding']
        path = root/ref['path']
        path.write_bytes(path.read_bytes()+b'\nTEST_ONLY_FINAL_DRIFT')
        return result
    monkeypatch.setattr(review, '_replacement_bear', drift)
    with pytest.raises(ValueError):
        review.build_source_native_economic_review(root=root,candidate_binding=baseline,
            replacement_candidate_binding=replacement)
