"""TEST_ONLY driver adapter fixtures; no model calls or real financial originals."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research.agent_review import operating_driver_draft_v2 as mod
from value_investment_agent.application.research.agent_review import operating_draft_v1 as v1
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 1, 8, tzinfo=timezone.utc)


@pytest.fixture
def context():
    return dict(symbol='123456', issuer_name='TEST_ONLY', as_of='2026-11-01',
        snapshot_fingerprint='a' * 64, evidence=[dict(id='test:1', source_id='TEST_ONLY',
            pdf_sha256='b' * 64, available_at='2026-10-30T00:00:00+00:00', period='2025-12-31',
            period_basis='FY', scope='consolidated', unit='CNY', field='revenue', value='100', text='TEST_ONLY')])


@pytest.fixture
def payload():
    capital = [dict(dimension=dimension, period_start='2027-01-01', period_end='2027-12-31',
        classification='UNKNOWN', lower=None, upper=None, unit='not_quantified',
        rationale='TEST_ONLY insufficient capital evidence', evidence_ids=['test:1']) for dimension in mod.CAPITAL]
    path = dict(baseline_period='2025-12-31', period_start='2027-01-01', period_end='2027-12-31',
        drivers={key: dict(lower='0.01', upper='0.02', rationale='TEST_ONLY conditional driver',
                          evidence_ids=['test:1']) for key in mod.DRIVERS}, capital_assumptions=capital)
    return dict(business_drivers=[dict(text='TEST_ONLY interpretation', evidence_ids=['test:1'])],
                operating_paths={name: deepcopy(path) for name in mod.SCENARIOS})


@pytest.fixture
def bridge(monkeypatch):
    """Contract stub isolates orchestration; it is not an alternative financial formula."""
    calls = []
    basis = dict(baselines={'2025-12-31': dict(period_basis='FY', fields={})}, comparisons=[])
    def build_basis(context):
        calls.append(('basis', deepcopy(context)))
        return deepcopy(basis)
    def calculate_path(received_basis, path):
        assert received_basis == basis
        calls.append(('path', deepcopy(path)))
        return dict(growth_range=dict(lower='0.13', upper='0.27'),
                    margin_range=dict(lower='0.18', upper='0.24'),
                    evidence_ids=['test:1'], baseline=dict(period=path['baseline_period']),
                    comparison_basis='CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY')
    def build_thresholds(derived):
        calls.append(('thresholds', deepcopy(derived)))
        return [dict(scenario='base', metric='revenue_growth', direction='BELOW', threshold='0.13')]
    stub = SimpleNamespace(build_basis=build_basis, calculate_path=calculate_path,
                           build_thresholds=build_thresholds, calls=calls)
    monkeypatch.setattr(mod, '_bridge', lambda: stub)
    return stub


def test_bridge_derived_ranges_v1_boundaries_and_capital_unknown(context, payload, bridge):
    before = deepcopy((context, payload))
    text = json.dumps(payload)
    result = mod.validate_response(LLMResponse(text, 200, 100, 'TEST_ONLY_MODEL'), 'FUNDAMENTAL', context, NOW)
    assert result['prompt_version'] == v1.PROMPT_VERSION
    assert result['driver_contract_version'] == 'operating-drivers-v2'
    assert result['response_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert result['usage'] == dict(prompt_tokens=200, completion_tokens=100)
    assert set(result['driver_bridge']) == {'version', 'basis', 'inputs', 'paths', 'thresholds', 'action'}
    assert result['driver_bridge']['version'] == 'operating-driver-bridge-v1'
    assert result['driver_bridge']['action'] == 'no_order'
    assert result['driver_bridge']['inputs'] == payload['operating_paths']
    assert set(result['driver_bridge']['paths']) == set(mod.SCENARIOS)
    assert result['driver_bridge']['thresholds'] == [dict(scenario='base', metric='revenue_growth', direction='BELOW', threshold='0.13')]
    for rows in result['draft']['scenarios'].values():
        assert [(r['dimension'], r['lower'], r['upper']) for r in rows[:2]] == [
            ('growth', '0.13', '0.27'), ('profit', '0.18', '0.24')]
        assert all(r['classification'] == 'UNKNOWN' and r['lower'] is None for r in rows[2:])
    assert result['context_sha256'] == v1._sha(mod.legacy_context(context))
    assert not result['formal_eligibility'] and not result['valuation_produced']
    assert result['action'] == 'no_order' and result['formal_fact_count'] == 0
    assert bridge.calls[0][1]['evidence'][0]['period_basis'] == 'FY'
    assert len([call for call in bridge.calls if call[0] == 'path']) == 3
    assert (context, payload) == before


@pytest.mark.parametrize('damage', ['missing_driver', 'extra_driver', 'unknown_ref', 'empty_refs',
    'duplicate_refs', 'nan', 'boolean', 'reversed', 'past', 'end_before_start', 'future_baseline',
    'missing_scenario', 'direct_margin', 'capital_duplicate', 'capital_period', 'capital_unknown_value',
    'capital_ref', 'business_ref'])
def test_invalid_driver_contract_rejected(context, payload, bridge, damage):
    path = payload['operating_paths']['base']
    driver = path['drivers']['volume_change']
    if damage == 'missing_driver': del path['drivers']['opex_change']
    elif damage == 'extra_driver': path['drivers']['margin'] = deepcopy(driver)
    elif damage == 'unknown_ref': driver['evidence_ids'] = ['invented']
    elif damage == 'empty_refs': driver['evidence_ids'] = []
    elif damage == 'duplicate_refs': driver['evidence_ids'] *= 2
    elif damage == 'nan': driver['lower'] = 'NaN'
    elif damage == 'boolean': driver['lower'] = True
    elif damage == 'reversed': driver['lower'] = '1'
    elif damage == 'past': path['period_start'] = '2026-01-01'
    elif damage == 'end_before_start': path['period_end'] = '2026-12-31'
    elif damage == 'future_baseline': path['baseline_period'] = '2027-12-31'
    elif damage == 'missing_scenario': del payload['operating_paths']['bull']
    elif damage == 'direct_margin': payload['scenarios'] = {}
    elif damage == 'capital_duplicate': path['capital_assumptions'][0]['dimension'] = 'terminal'
    elif damage == 'capital_period': path['capital_assumptions'][0]['period_end'] = '2028-12-31'
    elif damage == 'capital_unknown_value': path['capital_assumptions'][0]['lower'] = '0'
    elif damage == 'capital_ref': path['capital_assumptions'][0]['evidence_ids'] = ['invented']
    else: payload['business_drivers'][0]['evidence_ids'] = ['invented']
    with pytest.raises(ValueError):
        mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)


@pytest.mark.parametrize('text', ['not JSON', '{"operating_paths":{},"operating_paths":{}}', '{"x":NaN}'])
def test_json_rejection(context, bridge, text):
    with pytest.raises(ValueError): mod.validate_response(text, 'FUNDAMENTAL', context, NOW)


@pytest.mark.parametrize('role', ['COUNTER_EVIDENCE', 'EVENT'])
def test_request_proposal_strips_extensions_preserves_v1_schema(context, payload, bridge, role):
    proposal = mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    before = deepcopy(proposal)
    request = mod.build_request(role, context, fundamental_draft=proposal)
    assert request.output_schema == v1._schema(role, evidence_ids=v1._context(mod.legacy_context(context)))
    assert 'UNTRUSTED_NEW_PROPOSAL' in request.user and 'UNTRUSTED_NEW_DRIVER_BRIDGE' in request.user
    assert '仅结构化threshold为判定，文本不能代替' in request.user
    assert v1._canonical(mod._prompt_bridge(proposal['driver_bridge'])) in request.user
    assert proposal == before
    answer = dict(seen_events=[], uncovered=[dict(text='TEST_ONLY gap', evidence_ids=[])]) if role == 'EVENT' else dict(
        counterevidence=[dict(text='TEST_ONLY challenge', evidence_ids=['test:1'])],
        invalidation=[dict(text='TEST_ONLY condition', evidence_ids=['test:1'])])
    assert mod.validate_response(json.dumps(answer), role, context, NOW) == v1.validate_response(
        json.dumps(answer), role, mod.legacy_context(context), NOW)


def test_fundamental_request_driver_only_schema_and_economic_definitions(context, bridge):
    request = mod.build_request('FUNDAMENTAL', context)
    schema = request.output_schema
    assert set(schema['properties']) == {'business_drivers', 'operating_paths'}
    path = schema['properties']['operating_paths']['properties']['base']['properties']
    assert set(path['drivers']['properties']) == set(mod.DRIVERS)
    assert path['capital_assumptions']['items']['properties']['dimension']['enum'] == list(mod.CAPITAL)
    for phrase in ('sales activity index', 'overall cost-level change', 'selling plus administrative plus R&D',
                   'not income tax', 'not presumed recurring', 'stress envelope', 'relative_to_baseline'):
        assert phrase in request.system
    assert 'DETERMINISTIC_DRIVER_BASIS' in request.user
    assert context['evidence'][0]['period_basis'] == 'FY'
    assert 'period_basis' not in mod.legacy_context(context)['evidence'][0]


def test_domain_rejection_propagates_without_fallback(context, payload, bridge):
    def reject(basis, path):
        raise ValueError('TEST_ONLY_PERIOD_BASIS_MISMATCH')
    bridge.calculate_path = reject
    with pytest.raises(ValueError, match='PERIOD_BASIS_MISMATCH'):
        mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)


def native_contract_fixture(context, payload, kind):
    """Synthetic reported rows; actual domain API, never fabricated original files."""
    period = '2025-12-31' if kind == 'FY' else '2025-06-30'
    end = '2027-12-31' if kind == 'FY' else '2027-06-30'
    template = context['evidence'][0]
    context['evidence'] = [dict(template, id='test:1' if field == 'revenue' else 'test:' + field,
        field=field, value=value, period=period, period_basis=kind) for field, value in (
            ('revenue', '100'), ('cost', '60'), ('surcharges', '5'), ('selling', '10'),
            ('admin', '3'), ('research', '2'), ('pre_tax_profit', '20'))]
    for path in payload['operating_paths'].values():
        path.update(baseline_period=period, period_end=end)
        for key, driver in path['drivers'].items():
            value = '0.05' if key == 'surcharge_ratio' else '0.5' if key == 'fixed_cogs_share' else '0'
            driver.update(lower=value, upper=value)
        for row in path['capital_assumptions']:
            row['period_end'] = end
    return period


@pytest.mark.parametrize('kind', ['FY', 'H1'])
def test_actual_domain_api_derivation_thresholds_and_ce_requests(context, payload, kind):
    period = native_contract_fixture(context, payload, kind)
    original = deepcopy((context, payload))
    request = mod.build_request('FUNDAMENTAL', context)
    assert 'DETERMINISTIC_DRIVER_BASIS' in request.user
    result = mod.validate_response(LLMResponse(json.dumps(payload), 200, 100, 'TEST_ONLY'),
                                   'FUNDAMENTAL', context, NOW)
    packet = result['driver_bridge']
    assert packet['basis']['gaps'] == {}
    assert packet['basis']['baselines'][period]['other_pretax_cny'] == '0.00'
    assert len(packet['thresholds']) == 12
    assert set(packet) == {'version', 'basis', 'inputs', 'paths', 'thresholds', 'action'}
    assert packet['inputs'] == payload['operating_paths']
    for name, derived in packet['paths'].items():
        assert derived['corner_count'] == 128
        assert derived['growth_range'] == dict(lower='0.00', upper='0.00') or derived['growth_range'] == dict(lower='0', upper='0')
        from decimal import Decimal
        assert Decimal(derived['margin_range']['lower']) == Decimal('0.20')
        assert Decimal(derived['margin_range']['upper']) == Decimal('0.20')
        assert derived['baseline']['period'] == period and derived['period_basis'] == kind
        assert derived['comparison_basis'] == 'CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY'
        rows = result['draft']['scenarios'][name]
        assert rows[0]['lower'] == derived['growth_range']['lower']
        assert rows[1]['upper'] == derived['margin_range']['upper']
        assert len(rows[0]['evidence_ids']) == len(rows[1]['evidence_ids']) == 7
        assert rows[0]['period_start'] == rows[1]['period_start'] == derived['period_start']
        assert rows[0]['period_end'] == rows[1]['period_end'] == derived['period_end']
        assert all('独立角点包络' in row['rationale'] and '非概率、预测批准' in row['rationale'] for row in rows[:2])
        assert all(len(row['rationale']) <= 600 for row in rows)
        assert all(row['classification'] == 'UNKNOWN' for row in rows[2:])
    for threshold in packet['thresholds']:
        assert threshold['baseline_period'] == period and threshold['period_basis'] == kind
        assert threshold['meaning'] == 'REOPEN_RESEARCH_ONLY_NOT_AUTOMATIC_REVISION'
    for role in ('COUNTER_EVIDENCE', 'EVENT'):
        ce = mod.build_request(role, context, fundamental_draft=result)
        assert ce.output_schema == v1._schema(role, evidence_ids=v1._context(mod.legacy_context(context)))
        assert v1._canonical(mod._prompt_bridge(packet)) in ce.user
    assert (context, payload) == original


@pytest.mark.parametrize('damage', ['no_period_basis', 'fy_to_h1', 'duplicate', 'parent_cost', 'negative_sales'])
def test_actual_domain_rejects_unproven_or_mismatched_basis(context, payload, damage):
    native_contract_fixture(context, payload, 'FY')
    if damage == 'no_period_basis':
        for row in context['evidence']: del row['period_basis']
    elif damage == 'fy_to_h1':
        for path in payload['operating_paths'].values():
            path['period_end'] = '2027-06-30'
            for row in path['capital_assumptions']: row['period_end'] = '2027-06-30'
    elif damage == 'duplicate':
        context['evidence'].append(dict(context['evidence'][0], id='test:duplicate'))
    elif damage == 'parent_cost': context['evidence'][1]['scope'] = 'parent'
    else: payload['operating_paths']['base']['drivers']['volume_change']['lower'] = '-1'
    with pytest.raises(ValueError, match='VERIFIED_BASELINE_REQUIRED|CALENDAR_PLAN_MISMATCH|NONPOSITIVE_SALES_ACTIVITY'):
        mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)


@pytest.mark.parametrize('context_chars', [41000, 47507])
def test_compact_prompts_keep_full_ui_bridge_and_64k_limit(context, payload, context_chars):
    native_contract_fixture(context, payload, 'FY')
    template = context['evidence'][0]
    for index in range(89):
        row = dict(template, id=f'TEST_ONLY_narrative:{index}', text='TEST_ONLY public narrative',
                   unit='TEXT', scope='ISSUER_REPORTED_NARRATIVE')
        for key in ('value', 'field'): row.pop(key, None)
        context['evidence'].append(row)
    remaining = context_chars - len(v1._canonical(mod.legacy_context(context)))
    assert remaining > 0
    for row in context['evidence']:
        padding = min(remaining, 1500)
        row['text'] += '据' * padding
        remaining -= padding
        if not remaining: break
    assert remaining == 0
    assert len(context['evidence']) == 96
    assert len(v1._canonical(mod.legacy_context(context))) == context_chars
    if context_chars == 47507:
        assert len(v1._canonical(context)) > 48000
    for path in payload['operating_paths'].values():
        for driver in path['drivers'].values(): driver['rationale'] = '合成条件理由' * 30
    result = mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    bridge = result['driver_bridge']
    before = deepcopy(bridge)
    compact = mod._prompt_bridge(bridge)
    assert set(compact) == {'inputs', 'paths', 'thresholds'}
    for path in compact['paths'].values():
        assert set(path) == {'growth_range', 'margin_range', 'comparison_basis', 'baseline_period'}
    for drivers in compact['inputs'].values():
        assert set(drivers) == set(mod.DRIVERS)
        assert all(set(row) == {'lower', 'upper', 'rationale'} for row in drivers.values())
    assert all(set(row) == {'scenario', 'metric', 'direction', 'threshold'} for row in compact['thresholds'])
    assert len(v1._canonical(compact)) < len(v1._canonical(bridge))
    for role in mod.ROLES:
        request = mod.build_request(role, context, fundamental_draft=result if role != 'FUNDAMENTAL' else None)
        assert len(request.user) <= 64000
        if role != 'FUNDAMENTAL':
            appendix = request.user.split('UNTRUSTED_NEW_DRIVER_BRIDGE:', 1)[1]
            assert 'extrema' not in appendix and 'source_catalog' not in appendix
            assert 'pdf_sha256' not in appendix and 'evidence_ids' not in appendix
    assert bridge == before and 'extrema' in bridge['paths']['base']
    prompt = mod.build_request('FUNDAMENTAL', context)
    assert 'business_drivers at most 2' in prompt.system
    assert 'at most 40 Chinese characters' in prompt.system
    assert '1-3 necessary original evidence IDs' in prompt.system
    assert prompt.max_completion_tokens == 4096
    # The application still rejects oversized prompt projections; no limit relaxation.
    oversized = deepcopy(result)
    oversized['driver_bridge']['inputs']['base']['drivers']['volume_change']['rationale'] = 'x' * 64000
    with pytest.raises(ValueError, match='bounded prompt'):
        mod.build_request('COUNTER_EVIDENCE', context, fundamental_draft=oversized)


def test_prompt_basis_keeps_values_and_periods_without_repeated_metadata(context, payload):
    native_contract_fixture(context, payload, 'FY')
    basis = mod._bridge().build_basis(context)
    basis['comparisons'] = [dict(field=field, current_period='2025-12-31', prior_period='2024-12-31',
        current_value='100', prior_value='90', change_ratio='0.1', status='COMPARABLE',
        evidence_ids=['TEST_ONLY'], scope='consolidated', currency='CNY')
        for field in ('revenue', 'cost', 'selling', 'admin', 'research', 'pre_tax_profit', 'surcharges')]
    compact = mod._prompt_basis(basis)
    row = compact['baselines']['2025-12-31']
    assert set(row) == {'fields', 'period_basis', 'other_pretax_cny', 'pretax_margin'}
    assert row['fields'] == basis['baselines']['2025-12-31']['fields']
    assert row['period_basis'] == 'FY'
    assert len(compact['comparisons']) == 6
    assert all('evidence_ids' not in row and 'scope' not in row for row in compact['comparisons'])


def test_terminal_independent_future_period_preserves_h1_arithmetic(context, payload):
    native_contract_fixture(context, payload, 'H1')
    original = mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    for path in payload['operating_paths'].values():
        terminal = next(row for row in path['capital_assumptions'] if row['dimension'] == 'terminal')
        terminal.update(period_start='2030-01-01', period_end='2035-12-31')
    result = mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    assert result['driver_bridge']['paths'] == original['driver_bridge']['paths']
    assert result['driver_bridge']['thresholds'] == original['driver_bridge']['thresholds']
    for rows in result['draft']['scenarios'].values():
        terminal = next(row for row in rows if row['dimension'] == 'terminal')
        assert terminal['period_start'] == '2030-01-01' and terminal['period_end'] == '2035-12-31'
        assert terminal['classification'] == 'UNKNOWN' and terminal['lower'] is None
        assert rows[0]['period_end'] == rows[1]['period_end'] == '2027-06-30'
    assert 'independent farther-future period' in mod.build_request('FUNDAMENTAL', context).system
    terminal['period_start'] = '2026-01-01'
    payload['operating_paths']['base']['capital_assumptions'][-1]['period_start'] = '2026-01-01'
    with pytest.raises(ValueError, match='future forecast period'):
        mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)


@pytest.mark.parametrize('damage', ['baseline', 'start', 'end', 'fy_h1'])
def test_scenario_basis_mismatch_rejected_before_domain(context, payload, bridge, damage):
    path = payload['operating_paths']['bull']
    if damage == 'baseline': path['baseline_period'] = '2024-12-31'
    elif damage == 'start': path['period_start'] = '2028-01-01'; path['period_end'] = '2028-12-31'
    elif damage == 'end': path['period_end'] = '2028-12-31'
    else: path.update(baseline_period='2026-06-30', period_end='2027-06-30')
    for row in path['capital_assumptions']:
        if row['dimension'] != 'terminal':
            row.update(period_start=path['period_start'], period_end=path['period_end'])
    with pytest.raises(ValueError, match='^SCENARIO_BASIS_MISMATCH$'):
        mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    assert bridge.calls == []


def test_latest_complete_same_type_baseline_prompt(context, bridge):
    request = mod.build_request('FUNDAMENTAL', context)
    assert 'latest complete baseline' in request.system
    assert 'H1 2026 to H1 2027' in request.system
    assert 'identical baseline_period, period_start and period_end' in request.system


@pytest.mark.parametrize('damage', ['asof_start', 'wrong_year', 'fy_instead_h1', 'baseline_drift'])
def test_locked_calendar_rejects_uniform_wrong_dates_without_rewriting(context, payload, damage):
    native_contract_fixture(context, payload, 'H1')
    for path in payload['operating_paths'].values():
        if damage == 'asof_start': path['period_start'] = context['as_of']
        elif damage == 'wrong_year': path.update(period_start='2028-01-01', period_end='2028-06-30')
        elif damage == 'fy_instead_h1': path['period_end'] = '2027-12-31'
        else: path['baseline_period'] = '2024-06-30'
        for row in path['capital_assumptions']:
            if row['dimension'] != 'terminal':
                row.update(period_start=path['period_start'], period_end=path['period_end'])
    before = deepcopy(payload)
    with pytest.raises(ValueError, match='^CALENDAR_PLAN_MISMATCH$'):
        mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    assert payload == before


@pytest.mark.parametrize('kind', ['FY', 'H1'])
def test_calendar_schema_locks_latest_complete_baseline_and_next_year(context, payload, kind):
    period = native_contract_fixture(context, payload, kind)
    older = [dict(row, id=row['id'] + ':older', period='2024' + period[4:]) for row in context['evidence']]
    context['evidence'] += older
    # A newer incomplete period must not replace the latest complete baseline.
    context['evidence'].append(dict(context['evidence'][0], id='new:incomplete', period='2026-06-30', period_basis='H1'))
    request = mod.build_request('FUNDAMENTAL', context)
    expected = dict(baseline_period=period, period_start='2027-01-01',
                    period_end='2027-06-30' if kind == 'H1' else '2027-12-31')
    for schema in request.output_schema['properties']['operating_paths']['properties'].values():
        for key, value in expected.items():
            assert schema['properties'][key] == dict(type='string', const=value)
    assert v1._canonical(expected) in request.user
    assert 'calendar-locked' in request.system
    result = mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    assert result['driver_bridge']['inputs'] == payload['operating_paths']
