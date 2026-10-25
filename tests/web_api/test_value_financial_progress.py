"""Verified factual supplements never alter the published investment decision."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from test_read_api import _fixture
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.research import value_enrichment_batch
from value_investment_agent.application.product import pending_replay_publication
from value_investment_agent.application.product import pending_candidate_supplement
import pytest


def test_industrial_composition_survives_empty_financial_subsidiary_observations(tmp_path, monkeypatch):
    """Industrial notes are useful before complete debt or a finance subsidiary exists."""
    composition = dict(status='TEST_ONLY_PARTIAL_SCOPE', six_balance_buckets_cny='100.00',
                       complete_debt_verified=False, interest_bearing_debt=None)
    funding = dict(required_fields=[], observations=[], industrial_financing_composition=composition)
    summary = dict(status='VERIFIED_FACT_ADOPTION', symbol='000498', adopted_fact_count=0,
        research_inputs_updated=True, quality_coverage_before='0', quality_coverage_after='0',
        formal_eligibility=False, action='no_order', source_financial_funding_scope=funding)
    context = dict(case=SimpleNamespace(financial_summary={}))
    result = dict(adopted_points=[], evaluation_at='2026-10-25T00:00:00+00:00')
    monkeypatch.setattr(value_enrichment_batch, '_verified_registered_adoption',
        lambda *_a, **_kw: (deepcopy(summary), context, result))
    progress = value_enrichment_batch.read_verified_enrichment_progress(tmp_path, '000498', datetime.now(timezone.utc))
    assert progress['source_financial_funding_scope']['industrial_financing_composition'] == composition
    assert progress['adopted_metrics'] == []
    assert progress['formal_eligibility'] is False and progress['action'] == 'no_order'


def test_new_source_verified_candidate_can_be_read_without_formal_publication(tmp_path, monkeypatch):
    from value_investment_agent.application.discovery import value_candidate_selection
    payload = dict(candidate=dict(symbol='000498', company_name='TEST_ONLY',
        channels=['quality'], blockers=['MODEL_NOT_SELECTED']),
        financial_progress=dict(status='VERIFIED_FACT_ADOPTION', symbol='000498',
            research_inputs_updated=True, adopted_fact_count=1, formal_eligibility=False, action='no_order'),
        as_of='2026-10-25', scope='PUBLIC_FACTS_RESEARCH_NOT_DECISION',
        source_bindings=[], action='no_order', formal_eligibility=False)
    monkeypatch.setattr(value_candidate_selection, 'load_current_public_candidate_research',
        lambda **kwargs: deepcopy(payload) if kwargs['symbol'] == '000498' else None)
    with TestClient(create_app(tmp_path)) as client:
        actual = client.get('/api/v1/decisions/000498').json()
        assert actual['status'] == 'RESEARCH_ONLY'
        assert actual['decision']['candidate_action'] == 'no_order'
        assert actual['decision']['blockers'] == ['MODEL_NOT_SELECTED']
        assert actual['formal_eligibility'] is False
        assert actual['public_candidate_research']['scope'] == 'PUBLIC_FACTS_RESEARCH_NOT_DECISION'
        assert actual['publication']['publication_id'] is None
        assert client.get('/api/v1/decisions/600519').json()['decision'] is None


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


@pytest.mark.parametrize('invalid', [False, True])
def test_review_replay_does_not_rewrite_decision_or_publication(tmp_path, monkeypatch, invalid):
    _fixture(tmp_path)
    client = TestClient(create_app(tmp_path))
    original = client.get('/api/v1/decisions/600519').json()
    def read(**kw):
        assert kw['symbol'] == '600519'
        if invalid:
            raise ValueError('TEST_ONLY source drift')
        return dict(candidate=dict(candidate_research_as_of='2026-10-11', generated_at='2026-10-21'),
                    publication_binding=dict(path='runtime/TEST_ONLY.json', sha256='test'),
                    scope='UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY')
    monkeypatch.setattr(pending_replay_publication, 'load_current_pending_replay', read)
    actual = client.get('/api/v1/decisions/600519').json()
    assert actual['decision'] == original['decision']
    assert actual['review_replay']['formal_eligibility'] is False
    assert actual['review_replay']['status'] == ('SOURCE_UNAVAILABLE' if invalid else 'VERIFIED_EXACT_INPUT_REPLAY')
    assert actual['publication']['publication_id'] == original['publication']['publication_id']
    if not invalid:
        assert actual['review_replay']['research_as_of'] == '2026-10-11'
        assert actual['review_replay']['approval_changed'] is False


@pytest.mark.parametrize('invalid', [False, True])
def test_new_input_candidate_supersedes_only_review_materials_never_public_economics(tmp_path, monkeypatch, invalid):
    _fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        original = client.get('/api/v1/decisions/600519').json()

        def read(**kwargs):
            assert kwargs['symbol'] == '600519'
            if invalid:
                raise ValueError('TEST_ONLY changed registered supplement')
            return dict(candidate=dict(candidate_research_as_of='2026-10-21',
                valuation_basis_date='2026-10-20', valuation_basis_scope='EX_POST_PRIOR_COMPLETED_SESSION',
                generated_at='2026-10-21T15:00:00+00:00'),
                candidate_binding=dict(path='runtime/TEST_ONLY/candidate.json', sha256='0' * 64),
                scope='UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY')

        def forbidden(**kwargs):
            raise AssertionError('A configured supplement must never fall back to an old replay')

        monkeypatch.setattr(pending_candidate_supplement, 'load_current_pending_candidate_supplement', read)
        monkeypatch.setattr(pending_replay_publication, 'load_current_pending_replay', forbidden)
        actual = client.get('/api/v1/decisions/600519').json()
        assert actual['decision'] == original['decision']
        assert actual['publication']['publication_id'] == original['publication']['publication_id']
        status = actual['review_replay']
        assert status['status'] == ('SOURCE_UNAVAILABLE' if invalid else 'VERIFIED_NEW_INPUT_CANDIDATE')
        assert status['formal_eligibility'] is False
        if not invalid:
            assert status['research_as_of'] == '2026-10-21'
            assert status['valuation_basis_date'] == '2026-10-20'
            assert status['valuation_basis_scope'] == 'EX_POST_PRIOR_COMPLETED_SESSION'
            assert status['approval_changed'] is status['research_admitted'] is status['price_admitted'] is False
