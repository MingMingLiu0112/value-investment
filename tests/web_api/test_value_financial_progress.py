"""Verified factual supplements never alter the published investment decision."""
from copy import deepcopy

from fastapi.testclient import TestClient

from test_read_api import _fixture
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.research import value_enrichment_batch


def test_read_only_supplement_is_separate_from_published_decision(tmp_path, monkeypatch):
    _fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        original = client.get('/api/v1/decisions/600519').json()
        supplement = dict(status='VERIFIED_FACT_ADOPTION', action='no_order', symbol='600519',
            adopted_fact_count=1, research_inputs_updated=True, quality_coverage_before='0.5556',
            quality_coverage_after='0.6667', formal_eligibility=False)
        calls = []
        def read(**kwargs):
            calls.append(kwargs)
            return deepcopy(supplement)
        monkeypatch.setattr(value_enrichment_batch, 'read_verified_enrichment_progress', read)
        actual = client.get('/api/v1/decisions/600519').json()
        assert actual['financial_progress'] == supplement
        assert actual['decision'] == original['decision']
        # The fixture has no frozen publication; response generation time is
        # request-specific, while publication identity and economics must match.
        assert {k: v for k, v in actual['publication'].items() if k != 'generated_at'} == {
            k: v for k, v in original['publication'].items() if k != 'generated_at'}
        assert calls[0]['root'] == tmp_path
        assert calls[0]['symbol'] == '600519'
        assert calls[0]['evaluation_at'].utcoffset() is not None
        monkeypatch.setattr(value_enrichment_batch, 'read_verified_enrichment_progress', lambda **kw: None)
        assert client.get('/api/v1/decisions/600519').json()['financial_progress'] is None
