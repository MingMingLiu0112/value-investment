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
