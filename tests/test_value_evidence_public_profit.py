"""TEST_ONLY provider bytes plus official candidates; no debt/valuation approval."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import hashlib
import os
from pathlib import Path

import pytest

from test_value_evidence_enrichment_v1 import source
from test_public_financial_snapshot import collect, row
from value_investment_agent.application.research import value_evidence_enrichment_v1 as app
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as adapter


@pytest.fixture
def inputs(tmp_path, monkeypatch, source):
    # Only the PDF boundary is synthetic; the existing provider replay is real.
    candidates = [dict(field_name='net_income', unit='CNY', value='24', page=1,
        source_label='\u5f52\u5c5e\u4e8e\u6bcd\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da6',
        excerpt='TEST_ONLY parent profit 24', status='candidate_pending_automated_verification')]
    monkeypatch.setattr(adapter, 'extract_candidates_from_pages', lambda pages: deepcopy(candidates))
    binding, _ = collect(tmp_path, monkeypatch,
        rows=[dict(row('600887'), PARENT_NETPROFIT=24)])
    cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
    return source, binding, candidates, cutoff


def enrich(root, inputs, points=None):
    source, binding, _, cutoff = inputs
    return app.enrich_retained_company(root, source, points or [], evaluation_at=cutoff,
        cache_dir=root / '.tmp/public-profit', public_summary_binding=binding)


def test_automatic_profit_admission_does_not_require_debt_review(tmp_path, inputs):
    result = enrich(tmp_path, inputs)
    profit, = result['adopted_points']
    assert profit['field_name'] == 'net_income' and profit['value'] == '24'
    assert profit['metadata']['profit_basis'] == 'attributable_to_parent'
    assert profit['metadata']['automatic_cross_source_verification'] is True
    assert profit['human_reviewed'] is False
    assert profit['metadata']['economic_approval'] is False
    assert profit['metadata']['historical_pit_admission'] == 'NOT_ADMITTED'
    assert len(profit['metadata']['evidence_refs']) == 3
    assert result['public_profit_adoption']['status'] == 'FACT_ADMITTED'
    assert result['debt_scope']['value'] is None
    assert result['debt_scope']['complete_debt_verified'] is False
    assert result['adopted_debt_fact_ids'] == []
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    repeated = enrich(tmp_path, inputs)
    assert result['source_extraction']['reused'] is False
    assert repeated['source_extraction']['reused'] is True
    cold, warm = deepcopy(result), deepcopy(repeated)
    cold['source_extraction'].pop('reused')
    warm['source_extraction'].pop('reused')
    assert cold == warm


@pytest.mark.parametrize('fault', ['missing', 'conflict', 'ambiguous', 'unit', 'basis'])
def test_no_matching_official_fact_no_admission(tmp_path, inputs, fault):
    _, _, candidates, _ = inputs
    if fault == 'missing':
        candidates.clear()
    elif fault == 'conflict':
        candidates[0]['value'] = '25'
    elif fault == 'ambiguous':
        candidates.append(dict(candidates[0], value='23', page=2))
    elif fault == 'unit':
        candidates[0]['unit'] = 'CNY 10K'
    else:
        candidates[0]['source_label'] = '\u51c0\u5229\u6da6'
    result = enrich(tmp_path, inputs)
    assert result['adopted_points'] == []
    assert result['public_profit_adoption']['status'] in {'DATA_GAP', 'SOURCE_CONFLICT'}


def test_identical_summary_and_statement_rows_are_not_conflicting(tmp_path, inputs):
    inputs[2].append(dict(inputs[2][0]))
    assert enrich(tmp_path, inputs)['public_profit_adoption']['status'] == 'FACT_ADMITTED'


@pytest.mark.parametrize('value,status', [('24', 'EXISTING_ADMITTED_INPUT_PRESENT'),
                                        ('25', 'SOURCE_CONFLICT')])
def test_existing_admitted_profit_is_not_duplicated_or_overwritten(tmp_path, inputs, value, status):
    source, _, _, cutoff = inputs
    existing = dict(symbol=source.symbol, field_name='net_income', period_label=source.period,
        value=value, unit='CNY', data_point_id='TEST_ONLY-existing-parent-profit',
        source_id='TEST_ONLY-existing', created_at=source.available_at,
        validation_status='verified', metadata=dict(automatic_cross_source_verification=True,
                                                  statement_scope='consolidated'))
    before = deepcopy(existing)
    result = enrich(tmp_path, inputs, [existing])
    assert result['public_profit_adoption']['status'] == status
    assert result['adopted_points'] == []
    assert existing == before
    if status == 'SOURCE_CONFLICT':
        assert result['public_profit_adoption']['issues'] == ['EXISTING_ADMITTED_PARENT_PROFIT_CONFLICT']


@pytest.mark.parametrize('fault', ['manifest', 'page', 'official', 'future', 'other_symbol'])
def test_original_bytes_identity_and_cutoff_are_rechecked(tmp_path, inputs, fault):
    source, binding, _, cutoff = inputs
    manifest_path = tmp_path / binding['path']
    manifest = json.loads(manifest_path.read_bytes())
    if fault == 'manifest':
        manifest_path.write_bytes(manifest_path.read_bytes() + b' ')
    elif fault == 'page':
        path = tmp_path / manifest['pages'][0]['path']
        path.write_bytes(path.read_bytes() + b' ')
    elif fault == 'official':
        (tmp_path / source.path).write_bytes(b'changed TEST_ONLY original')
    elif fault == 'future':
        inputs = source, binding, inputs[2], cutoff - timedelta(days=1)
    else:
        from dataclasses import replace
        source = replace(source, symbol='600519')
        monkey_inputs = source, binding, inputs[2], cutoff
        with pytest.raises(ValueError, match='security identity'):
            enrich(tmp_path, monkey_inputs)
        return
    with pytest.raises(ValueError):
        enrich(tmp_path, inputs)


def test_warm_replay_regenerates_profit_instead_of_trusting_flags(tmp_path, inputs):
    source, _, _, cutoff = inputs
    accepted = enrich(tmp_path, inputs)['adopted_points']
    merged, _ = app.consume_retained_enrichment(tmp_path, accepted, [asdict(source)], evaluation_at=cutoff)
    assert merged == accepted
    repeat, _ = app.consume_retained_enrichment(tmp_path, merged, [asdict(source)], evaluation_at=cutoff)
    assert repeat == merged
    forged = deepcopy(accepted)
    forged[0]['value'] = '999'
    replay, _ = app.consume_retained_enrichment(tmp_path, forged, [asdict(source)], evaluation_at=cutoff)
    assert replay[0]['value'] == '24'
    manifest = json.loads((tmp_path / inputs[1]['path']).read_bytes())
    path = tmp_path / manifest['pages'][0]['path']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='original hash'):
        app.consume_retained_enrichment(tmp_path, merged, [asdict(source)], evaluation_at=cutoff)


def test_profit_enters_existing_typed_research_without_valuation_approval(tmp_path, inputs):
    from value_investment_agent.research_case import ResearchCase
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.valuation_models.fcff import FinancialFacts
    source, _, _, cutoff = inputs
    result = enrich(tmp_path, inputs)
    case = ResearchCase(symbol=source.symbol, name='TEST_ONLY', as_of=cutoff.date(),
        generated_at=cutoff, run_id='test', research_version='test-v1', industry='TEST_ONLY',
        investment_path='UNASSESSED', thesis='TEST_ONLY', return_driver='UNASSESSED',
        mispricing_hypothesis='UNASSESSED', financial_summary={}, positives=[], counter_evidence=[],
        thesis_breakers=[], next_events=[], evidence_status='PARTIAL', valuation_status='NOT_ASSESSED',
        research_status='DATA_CHECK', blockers=['MISSING_ECONOMIC_INPUTS'], evidence_refs=[],
        quote_date=None, financial_period=datetime.fromisoformat(source.period).date(),
        missing_date_reasons={'quote_date': 'No quote used by this test'})
    facts = FinancialFacts(source.symbol, cutoff.date(), False, [], ['MISSING_ECONOMIC_INPUTS'])
    repository = InMemoryResearchArtifactRepository()
    kwargs = dict(root=tmp_path, points=[], repository=repository, case=case, facts=facts, run_id='test')
    admitted = app.register_enriched_research(result, **kwargs)
    assert admitted['consumed_operating_inputs']['net_income'] == Decimal('24')
    assert admitted['formal_eligibility'] is False
    assert admitted['economic_admission'] == 'NOT_PROVEN'
    assert admitted == app.register_enriched_research(result, **kwargs)
    forged = deepcopy(result)
    forged['adopted_points'][0]['value'] = '25'
    with pytest.raises(ValueError, match='revalidated source facts'):
        app.register_enriched_research(forged, **kwargs)


@pytest.mark.parametrize('symbol,expected', [('000544', '1075151300.84'),
                                          ('600741', '7207268139.61')])
def test_real_official_profit_and_public_originals_replay(symbol, expected):
    location = os.environ.get('PUBLIC_PROFIT_REAL_ROOT')
    if not location:
        pytest.skip('Optional retained public originals were not supplied')
    root = Path(location).resolve()
    binding = dict(path='runtime/public-financial-autonomous/20261025T000551148238Z/manifest.json',
        sha256='87d339034bb62ad2e786353fb6b883996a63267c35877535bd6f4d53118285f8')
    if symbol == '000544':
        receipt = root / ('runtime/screened-candidate-research/'
            '000544-20261024T131028035625Z-cc87470a/acquisition-receipt.json')
        fact = json.loads(receipt.read_bytes())['sources'][0]
        official = adapter.RetainedAnnualSource(symbol, '2025-12-31', fact['local_path'],
            fact['sha256'], fact['location'], fact['source_available_at'])
    else:
        directory = root / 'runtime/m2-pending-600741-20261012-final-v1'
        fact = json.loads((directory / 'pending-research.json').read_bytes())
        official = adapter.RetainedAnnualSource(symbol, '2025-12-31',
            (directory / 'annual-report.pdf').relative_to(root).as_posix(),
            fact['source_sha256'], fact['source_url'], fact['official_index_pages'][-1]['acquired_at'])
    before = hashlib.sha256((root / official.path).read_bytes()).hexdigest()
    cutoff = datetime.now(timezone.utc)
    result = app.enrich_retained_company(root, official, [], evaluation_at=cutoff,
        cache_dir=root / '.tmp/public-profit-real-test', public_summary_binding=binding)
    profit, = result['adopted_points']
    assert profit['value'] == expected
    assert result['public_profit_adoption']['status'] == 'FACT_ADMITTED'
    assert len([ref for ref in profit['metadata']['evidence_refs'] if 'page' in ref]) == 2
    replay, _ = app.consume_retained_enrichment(root, [profit], [asdict(official)], evaluation_at=cutoff)
    assert replay == [profit]
    assert hashlib.sha256((root / official.path).read_bytes()).hexdigest() == before
    assert result['debt_scope']['value'] is None
    assert result['debt_scope']['complete_debt_verified'] is False
    assert result['formal_eligibility'] is False
