"""TEST_ONLY transport; no live provider execution or real-source acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from value_investment_agent.application.research.agent_review import operating_draft_v1 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest, LLMResponse

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


@pytest.fixture
def context():
    return dict(symbol='123456', issuer_name='TEST_ONLY company', as_of='2026-10-31',
        snapshot_fingerprint='a' * 64, evidence=[dict(id='row:1', source_id='official:1',
        pdf_sha256='b' * 64, available_at='2026-10-30T00:00:00+00:00', period='2026-06-30',
        scope='consolidated', unit='CNY', text='TEST_ONLY demand weakened.', value='10')])


def output(role):
    statement = dict(text='TEST_ONLY conditional interpretation, requires investigation.', evidence_ids=['row:1'])
    if role == 'COUNTER_EVIDENCE':
        return dict(counterevidence=[deepcopy(statement)], invalidation=[deepcopy(statement)])
    if role == 'EVENT':
        return dict(seen_events=[], uncovered=[dict(text='No subsequent filings were supplied.', evidence_ids=[])])
    rows = [dict(dimension=dimension, period_start='2027-01-01', period_end='2027-12-31',
        classification='FORECAST', lower='0.01', upper='0.03', unit='ratio',
        rationale='TEST_ONLY hypothesis; source is not a forecast.', evidence_ids=['row:1'])
        for dimension in mod.DIMENSIONS]
    rows[-1].update(classification='UNKNOWN', lower=None, upper=None, unit='not_quantified',
                    rationale='Economic persistence has not been established.')
    return dict(business_drivers=[statement], scenarios={name: deepcopy(rows) for name in ('bear', 'base', 'bull')})


@pytest.mark.parametrize('role', mod.ROLES)
def test_independent_role_request_and_source_bound_draft(context, role):
    original = deepcopy(context)
    request = mod.build_request(role, context)
    assert isinstance(request, LLMRequest) and request.max_completion_tokens == 4096
    assert 'untrusted data' in request.system and 'row:1' in request.user
    payload = output(role)
    response = LLMResponse(json.dumps(payload), 1000, 800, 'TEST_ONLY_MODEL')
    result = mod.validate_response(response, role, context, NOW)
    assert result['draft'] == payload and result['source_bindings'][0]['pdf_sha256'] == 'b' * 64
    assert result['action'] == 'no_order' and result['formal_fact_count'] == result['approval_count'] == 0
    assert not result['valuation_produced'] and not result['formal_eligibility']
    assert not result['decision_changed'] and not result['provider_execution_attested']
    assert context == original
    assert mod.validate_response(json.dumps(payload), role, context, NOW)['model_id'] is None


@pytest.mark.parametrize('damage', ['citation', 'empty_citation', 'missing_base', 'missing_dimension',
    'duplicate_dimension', 'reported', 'unknown_value', 'nan', 'infinite', 'reverse', 'bool',
    'past', 'period_order', 'unit', 'approval', 'valuation', 'extra_row', 'rationale'])
def test_bad_fundamental_drafts_rejected(context, damage):
    payload = output('FUNDAMENTAL')
    row = payload['scenarios']['base'][0]
    if damage == 'citation': row['evidence_ids'] = ['unknown']
    elif damage == 'empty_citation': row['evidence_ids'] = []
    elif damage == 'missing_base': del payload['scenarios']['base']
    elif damage == 'missing_dimension': payload['scenarios']['base'].pop()
    elif damage == 'duplicate_dimension': row['dimension'] = 'terminal'
    elif damage == 'reported': row['classification'] = 'REPORTED_FACT'
    elif damage == 'unknown_value': row['classification'] = 'UNKNOWN'
    elif damage == 'nan': row['lower'] = 'NaN'
    elif damage == 'infinite': row['upper'] = 'Infinity'
    elif damage == 'reverse': row['lower'] = '5'
    elif damage == 'bool': row['lower'] = True
    elif damage == 'past': row['period_start'] = '2026-01-01'
    elif damage == 'period_order': row['period_end'] = '2026-12-31'
    elif damage == 'unit': row['unit'] = 'not_quantified'
    elif damage == 'approval': payload['approved'] = True
    elif damage == 'valuation': payload['fair_value'] = '100'
    elif damage == 'extra_row': row['fact'] = True
    else: row['rationale'] = ''
    with pytest.raises(ValueError): mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)


@pytest.mark.parametrize('damage', ['future', 'hash', 'duplicate', 'old_thesis', 'missing_scope',
    'scalar_nan', 'scalar_bool', 'empty', 'future_period', 'timezone', 'prior_generation'])
def test_invalid_source_context_rejected(context, damage):
    row = context['evidence'][0]
    if damage == 'future': row['available_at'] = '2027-01-01T00:00:00+00:00'
    elif damage == 'hash': row['pdf_sha256'] = 'fake'
    elif damage == 'duplicate': context['evidence'].append(deepcopy(row))
    elif damage == 'old_thesis': context['thesis'] = 'Old package thesis'
    elif damage == 'missing_scope': del row['scope']
    elif damage == 'scalar_nan': row['value'] = 'NaN'
    elif damage == 'scalar_bool': row['value'] = True
    elif damage == 'empty': context['evidence'] = []
    elif damage == 'future_period': row['period'] = '2027-01-01'
    elif damage == 'timezone': row['available_at'] = '2026-10-30T00:00:00'
    else:
        with pytest.raises(ValueError):
            mod.validate_response(json.dumps(output('EVENT')), 'EVENT', context,
                                  datetime(2026, 10, 29, tzinfo=timezone.utc))
        return
    with pytest.raises(ValueError): mod.build_request('FUNDAMENTAL', context)


@pytest.mark.parametrize('damage', ['tools', 'usage', 'duplicate_json', 'role', 'empty_counter', 'event_unseen'])
def test_response_limits_and_role_boundaries(context, damage):
    role = 'COUNTER_EVIDENCE'
    payload = output(role)
    response = json.dumps(payload)
    if damage == 'tools': response = LLMResponse(response, 10, 10, 'TEST_ONLY', 1)
    elif damage == 'usage': response = LLMResponse(response, 10, 4097, 'TEST_ONLY')
    elif damage == 'duplicate_json': response = '{"counterevidence":[],"counterevidence":[]}'
    elif damage == 'role': role = 'EVENT'
    elif damage == 'empty_counter': payload['counterevidence'] = []; response = json.dumps(payload)
    else:
        role = 'EVENT'; payload = output(role)
        payload['seen_events'] = [dict(text='Unseen event claimed', evidence_ids=[])]
        response = json.dumps(payload)
    with pytest.raises(ValueError): mod.validate_response(response, role, context, NOW)


def test_unknown_not_zero_and_request_budget(context):
    payload = output('FUNDAMENTAL')
    result = mod.validate_response(json.dumps(payload), 'FUNDAMENTAL', context, NOW)
    assert result['draft']['scenarios']['base'][-1]['lower'] is None
    assert mod.build_request('EVENT', context, 512).max_completion_tokens == 512
    with pytest.raises(ValueError): mod.build_request('EVENT', context, 4097)


@pytest.mark.parametrize('role', ['COUNTER_EVIDENCE', 'EVENT'])
def test_new_fundamental_proposal_is_revalidated_untrusted_and_request_bound(context, role):
    proposal = mod.validate_response(json.dumps(output('FUNDAMENTAL')), 'FUNDAMENTAL', context, NOW)
    before = deepcopy((context, proposal))
    original = mod.build_request(role, context)
    request = mod.build_request(role, context, fundamental_draft=proposal)
    assert 'UNTRUSTED_NEW_PROPOSAL' in request.user and 'Economic persistence' in request.user
    assert 'Simplified Chinese' in request.system
    assert request.user != original.user and request.output_schema == original.output_schema
    assert mod.build_request(role, context, fundamental_draft=proposal) == request
    proposal['draft']['business_drivers'][0]['text'] = 'A different new hypothesis'
    assert mod.build_request(role, context, fundamental_draft=proposal).user != request.user
    assert context == before[0]
    assert mod.validate_response(json.dumps(output(role)), role, context, NOW)['draft'] == output(role)


@pytest.mark.parametrize('damage', ['role', 'symbol', 'fingerprint', 'context_hash', 'source_hash',
    'source_time', 'status', 'citation', 'missing_base', 'approval', 'package', 'thesis', 'fundamental'])
def test_foreign_or_admitted_or_malformed_proposal_rejected(context, damage):
    proposal = mod.validate_response(json.dumps(output('FUNDAMENTAL')), 'FUNDAMENTAL', context, NOW)
    role = 'COUNTER_EVIDENCE'
    if damage == 'role': proposal['role'] = 'EVENT'
    elif damage == 'symbol': proposal['symbol'] = '654321'
    elif damage == 'fingerprint': proposal['snapshot_fingerprint'] = 'c' * 64
    elif damage == 'context_hash': proposal['context_sha256'] = 'c' * 64
    elif damage == 'source_hash': proposal['source_bindings'][0]['pdf_sha256'] = 'c' * 64
    elif damage == 'source_time': proposal['source_bindings'][0]['available_at'] = '2026-10-29T00:00:00+00:00'
    elif damage == 'status': proposal['status'] = 'APPROVED'
    elif damage == 'citation': proposal['draft']['scenarios']['base'][0]['evidence_ids'] = ['unseen']
    elif damage == 'missing_base': del proposal['draft']['scenarios']['base']
    elif damage == 'approval': proposal['approval_count'] = 1
    elif damage == 'package': proposal['old_package'] = {}
    elif damage == 'thesis': proposal['thesis'] = 'old thesis'
    else: role = 'FUNDAMENTAL'
    with pytest.raises(ValueError): mod.build_request(role, context, fundamental_draft=proposal)


@pytest.mark.parametrize('role', ['COUNTER_EVIDENCE', 'EVENT'])
def test_91_source_40k_context_proposal_fits_without_duplicate_catalog_but_checks_hash(context, role):
    """TEST_ONLY near-production size; all provenance remains checked, not resent."""
    template = deepcopy(context['evidence'][0])
    context['evidence'] = [dict(template,
        id='row:1' if index == 0 else f'native-fact-{index}-' + 'f' * 40,
        source_id=f'official-source-{index}-' + 's' * 25)
        for index in range(91)]
    # Use canonical character length, matching the production prompt guard.
    # Padding is synthetic source text, not additional forecast parameters.
    remaining = 41000 - len(mod._canonical(context))
    assert remaining > 0
    for row in context['evidence']:
        padding = min(remaining, 1900)
        row['text'] += '据' * padding
        remaining -= padding
        if remaining == 0:
            break
    assert remaining == 0 and len(mod._canonical(context)) == 41000
    before = deepcopy(context)
    proposal = mod.validate_response(json.dumps(output('FUNDAMENTAL')), 'FUNDAMENTAL', context, NOW)
    assert len(proposal['source_bindings']) == 91
    request = mod.build_request(role, context, fundamental_draft=proposal)
    assert 41000 < len(request.user) < 64000
    assert 'UNTRUSTED_NEW_PROPOSAL' in request.user
    assert '"source_bindings"' not in request.user
    # This size would exceed the old bound if the full catalog were resent.
    redundant = len('"source_bindings":') + len(mod._canonical(proposal['source_bindings'])) + 1
    assert len(request.user) + redundant > 64000
    assert request == mod.build_request(role, context, fundamental_draft=proposal)
    assert context == before
    corrupted = deepcopy(proposal)
    corrupted['source_bindings'][-1]['pdf_sha256'] = 'c' * 64
    with pytest.raises(ValueError, match='issuer/source/status mismatch'):
        mod.build_request(role, context, fundamental_draft=corrupted)


def test_prompt_context_91_rows_is_lossless_scope_aware_and_smaller(context):
    template = deepcopy(context['evidence'][0])
    rows = []
    for index in range(91):
        source = index % 2
        row = dict(template, id='row:1' if index == 0 else f'fact-or-excerpt:{index}',
                   source_id=f'official:{source}', pdf_sha256=('b' if source == 0 else 'c') * 64,
                   scope='parent' if index % 3 == 0 else 'consolidated',
                   text='仅为合成规模测试，保留原文和数值，不作经济事实。' * 4)
        if index >= 84:
            row.pop('value')
            row.update(scope='ISSUER_REPORTED_NARRATIVE', unit='TEXT')
        rows.append(row)
    context['evidence'] = rows
    remaining = 41000 - len(mod._canonical(context))
    assert remaining > 0
    for row in rows:
        padding = min(remaining, 1600)
        row['text'] += '据' * padding
        remaining -= padding
        if remaining == 0:
            break
    assert remaining == 0
    original = deepcopy(context)
    view = mod._prompt_context(context)
    assert len(view['evidence']) == 91 and len(view['source_catalog']) == 2
    assert len(mod._canonical(view)) < len(mod._canonical(context)) - 8000
    for old, projected in zip(rows, view['evidence']):
        metadata = view['source_catalog'][projected['source_ref']]
        assert metadata['source_id'] == projected['source_id'] == old['source_id']
        restored = {key: value for key, value in projected.items() if key != 'source_ref'}
        restored.update(metadata)
        assert restored == old
    assert context == original
    for role in mod.ROLES:
        request = mod.build_request(role, context)
        assert 'Parent-only CapEx is not a group project budget' in request.system
        assert 'investment must be UNKNOWN' in request.system
        assert 'inventory is not dealer/channel' in request.system
        assert 'comparison baseline' in request.system
        assert mod._canonical(view) in request.user
    proposal = mod.validate_response(json.dumps(output('FUNDAMENTAL')), 'FUNDAMENTAL', context, NOW)
    assert proposal['prompt_version'] == mod.PROMPT_VERSION
    assert len(proposal['source_bindings']) == 91
    assert proposal['context_sha256'] == mod._sha(context)
    for role in ('COUNTER_EVIDENCE', 'EVENT'):
        request = mod.build_request(role, context, fundamental_draft=proposal)
        assert len(request.user) < 64000
        corrupt = deepcopy(proposal)
        corrupt['source_bindings'][-1]['pdf_sha256'] = 'd' * 64
        with pytest.raises(ValueError): mod.build_request(role, context, fundamental_draft=corrupt)
    corrupt = deepcopy(proposal)
    corrupt['prompt_version'] = 'old-prompt'
    with pytest.raises(ValueError): mod.build_request('COUNTER_EVIDENCE', context, fundamental_draft=corrupt)
    del corrupt['prompt_version']
    with pytest.raises(ValueError): mod.build_request('EVENT', context, fundamental_draft=corrupt)


def test_prompt_catalog_disambiguates_same_source_id_hash_and_time(context):
    first = context['evidence'][0]
    context['evidence'] += [dict(first, id='row:2', pdf_sha256='c' * 64),
                            dict(first, id='row:3', available_at='2026-10-29T00:00:00+00:00')]
    view = mod._prompt_context(context)
    assert len(view['source_catalog']) == 3
    assert len({row['source_ref'] for row in view['evidence']}) == 3
    context['evidence'][-1]['available_at'] = '2027-01-01T00:00:00+00:00'
    with pytest.raises(ValueError): mod.build_request('EVENT', context)
