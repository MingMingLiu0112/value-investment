"""Current economic assessment consumes source-matched historical drivers only."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import value_economic_assessment as module


def test_unsupported_research_does_not_create_an_operating_appendix(tmp_path):
    assert module._current_operating_bridge(tmp_path, dict(symbol='000333'), None,
                                          datetime.now(timezone.utc)) is None


@pytest.mark.parametrize('fault', ['scope', 'source', 'issuer', 'anchor', 'drift'])
def test_operating_appendix_refuses_unmatched_context_without_numbers(tmp_path, monkeypatch, fault):
    path = tmp_path / 'docs/current/two-company-earnings-bridge-20261024/sources.json'
    path.parent.mkdir(parents=True)
    spec = dict(schema_version='two-company-earnings-source-spec-v1',
        scope='RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION', action='no_order',
        common_fields=[], companies={'600887': [dict(symbol='600887', source_id='official',
            sha256='a' * 64, extra_fields=[])]})
    analysis = dict(symbol='600887', source_catalog=[dict(id='official', sha256='a' * 64)])
    if fault == 'scope':
        spec['scope'] = 'TEST_ONLY_WRONG_SCOPE'
    elif fault == 'source':
        analysis['source_catalog'][0]['sha256'] = 'b' * 64
    elif fault == 'issuer':
        spec['companies']['600887'][0]['symbol'] = '600519'
    path.write_text(json.dumps(spec), encoding='utf-8')

    def compute(**_):
        if fault == 'drift':
            path.write_text('{}', encoding='utf-8')
        return dict(ttm=dict(lines_cny=dict(ex_parent_profit='100')))

    monkeypatch.setattr(module, 'research_from_retained_sources', compute)
    result = module._current_operating_bridge(tmp_path, analysis,
                                             Decimal('100' if fault == 'drift' else '200'),
                                             datetime.now(timezone.utc))
    assert result['status'] == ({'source': 'SOURCES_DIFFER_FROM_CURRENT_RESEARCH',
        'issuer': 'SOURCES_DIFFER_FROM_CURRENT_RESEARCH', 'anchor': 'HISTORICAL_ANCHOR_MISMATCH'}
        .get(fault, 'SOURCE_REVALIDATION_FAILED'))
    assert 'h1_change' not in result and 'historical_ttm_cny' not in result
    assert result['normalized_parent_profit_cny'] is None
    assert result['g3_changed'] is result['strategy_admitted'] is False


@pytest.mark.skipif(not os.environ.get('EARNINGS_BRIDGE_REAL_ROOT'),
                    reason='Explicit retained official PDF root required')
@pytest.mark.parametrize('symbol,ttm', [('600519', '81367067677.44'), ('600887', '9647734710.01')])
def test_actual_current_assessment_recomputes_original_drivers_without_admission(symbol, ttm):
    root = Path(os.environ['EARNINGS_BRIDGE_REAL_ROOT'])
    result = module.load_current_value_economic_assessment(root=root, symbol=symbol,
        now=datetime.now(timezone.utc))
    bridge = result['earnings']['operating_quality_bridge']
    assert bridge['status'] == 'SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED'
    assert bridge['symbol'] == symbol
    assert bridge['historical_ttm_cny'] == ttm
    assert bridge['input_descriptor_sha256'] == result['input_descriptor_sha256']
    assert bridge['candidate_binding'] == result['review_binding']['candidate_binding']
    assert bridge['normalized_parent_profit_cny'] is bridge['normalized_range'] is None
    assert bridge['g3_changed'] is bridge['strategy_admitted'] is bridge['price_admitted'] is False
    assert result['primary_valuation_usable'] is result['approval_changed'] is False
    for period in ('h1_change', 'annual_change'):
        change = bridge[period]
        assert Decimal(change['arithmetic_residual_cny']) == 0
        assert sum(Decimal(row['contribution_cny']) for row in change['rows']) == Decimal(change['computed_change_cny'])
    for source in bridge['source_bindings']:
        assert dict(path=source['path'], sha256=source['sha256']) in result['source_bindings']
    assert bridge['source_spec_binding'] in result['source_bindings']
