"""Native signed research -> native partial replay -> actual shared quote bridge.

Economics, keys, HTTP bodies, prices and policy authorization are TEST_ONLY.
No baseline, Gate, approval resolver, evaluator or bridge implementation is stubbed.
"""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json

import pytest

from test_current_snapshot_validity import native_snapshot, synthetic_chain
from test_incremental_validity import _write
from test_quote_sessions import sse_evidence
from value_investment_agent.application.product import current_snapshot_validity as service
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.quote_bridge import (
    CurrentSnapshotBridgeContext, execute_quote_bridge_for_symbol,
)
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
from value_investment_agent.research_run_contract import valuation_result_sha256


@pytest.fixture
def consumer(native_snapshot):
    case = native_snapshot
    root, now = case['root'], case['now']
    with _use_test_trust_registry(root/'TEST_ONLY-combined-trust-registry.json'):
        baseline = service._replay_approved_baseline(root, json.loads(case['package_path'].read_bytes()),
                                                   case['reviews_ref'], now)
    policy = dict(schema_version=service.POLICY_SCHEMA, scope=service.SCOPE, action='no_order', symbol='600519',
        rule='ZERO_NEW_OR_CHANGED_FILINGS', baseline_package=case['package_ref'], baseline_reviews=case['reviews_ref'],
        approval_id=baseline.approval_id, approval_transport=baseline.approval_transport,
        approval_set=baseline.approval_set, model_id=baseline.validity.model_id,
        model_version=baseline.valuation.model_version, rule_version=baseline.rule_version,
        research_version=baseline.research_version, valuation_sha256=valuation_result_sha256(baseline.valuation),
        max_snapshot_age_seconds=600, valid_from='2026-09-21T10:00:00+00:00',
        valid_until='2026-09-21T11:00:00+00:00', confirmed_at='2026-09-21T10:01:00+00:00')
    policy_ref = dict(path='runtime/TEST_ONLY-consumer-policy.json',
        sha256=_write(root/'runtime/TEST_ONLY-consumer-policy.json', policy))
    packet = sse_evidence(price=5, day='2026-09-21')
    documents, refs = {}, {}
    for role in ('tencent', 'sina', 'calendar_documents'):
        values = packet[role] if role == 'calendar_documents' else [packet[role]]
        ids = []
        for value in values:
            value = dict(value, http_status=200)
            identity = hashlib.sha256((value['source_url']+'\n'+value['fetched_at']+'\n'+value['sha256']).encode()).hexdigest()
            documents[identity] = value
            ids.append(identity)
        refs[role] = ids if role == 'calendar_documents' else ids[0]
    bundle = root/'runtime/TEST_ONLY-consumer-quote.json'
    _write(bundle, dict(version='quote-session-collection-v1', status='collected_not_verified',
        finished_at='2026-09-21T08:00:00+00:00', documents=documents,
        references={'600519': dict(symbol='600519', calendar_exchange='SSE', document_refs=refs)}))
    pointer = root/'config/current-quote-bridge.json'
    content = json.loads(pointer.read_bytes())
    content['quotes']['600519'].update(quote_bundle=bundle.relative_to(root).as_posix(),
        quote_bundle_sha256=sha256_file(bundle), incremental_validity_binding=case['binding_ref'])
    _write(pointer, content)
    return dict(case, baseline=baseline, policy=policy, bundle=bundle, pointer=pointer,
        context=CurrentSnapshotBridgeContext(policy_ref, case['reviews_ref'], lambda **kwargs: True))


def execute(case, **kwargs):
    with _use_test_trust_registry(case['root']/'TEST_ONLY-combined-trust-registry.json'):
        return execute_quote_bridge_for_symbol(case['root'], '600519',
            today=kwargs.pop('today', case['now']),
            current_snapshot_context=kwargs.pop('context', case['context']), **kwargs)


def test_native_entrypoint_reaches_shared_bridge_with_explicit_asof_scope(consumer):
    case = consumer
    package_before = case['package_path'].read_bytes()
    pointer_before = case['pointer'].read_bytes()
    authorizations = []
    def authorize(**kwargs):
        authorizations.append(kwargs['policy_binding'])
        return True
    result = execute(case, context=replace(case['context'], authorize_policy=authorize))
    assert result['status'] == 'QUOTE_VERIFIED_WITH_CURRENT_ASOF_SNAPSHOT', result['reason']
    assert result['price_comparison']['bridge_status'] == 'READY'
    assert result['price_admitted'] is True
    assert len(authorizations) == 4  # Two complete evaluations, each with final authorization.
    assert result['conditional_valuation'] == json.loads(case['baseline'].valuation.to_json())
    assert result['research_day'] == '2026-09-21'
    assert result['quote']['latest_completed_session'] == '2026-09-21'
    for envelope in (result, result['price_comparison'], result['current_event_coverage'],
                     result['compatibility']['comparison_eligible'], result['current_snapshot_validity']):
        assert envelope['scope'] == service.SCOPE
        assert envelope['knowledge_as_of'] == case['now'].isoformat()
        assert envelope['observed_at'] == (case['now']-timedelta(minutes=1)).isoformat()
        assert envelope['full_calendar_window_elapsed'] is False
        assert envelope['formal_eligibility'] is False
        assert envelope['action'] == 'no_order'
    assert result['current_event_coverage']['covered_through'] is None
    assert result['research_comparison_only'] is True
    assert result['price_comparison']['strict_contemporaneous_pit'] is False
    assert result['compatibility']['formal_decision_eligible']['eligible'] is False
    assert case['package_path'].read_bytes() == package_before
    assert case['pointer'].read_bytes() == pointer_before
    assert execute(case, context=None)['status'] == 'INCREMENTAL_VALIDITY_BLOCKED'


@pytest.mark.parametrize('change', ['source', 'policy_missing', 'policy_expired', 'pending_reviews',
    'dict_context', 'bool_authorizer', 'revoked_second_replay', 'observation_last_auth', 'scan_last_auth',
    'pointer_last_auth', 'quote_last_auth', 'approval_last_auth', 'policy_last_auth'])
def test_scoped_consumer_drift_and_missing_authority_fail_closed(consumer, change):
    case = consumer
    context = case['context']
    if change == 'source':
        next((case['root']/'runtime/native-partial/raw-index').glob('*.bin')).write_bytes(b'TEST_ONLY_DRIFT')
    elif change == 'policy_missing':
        context = replace(context, policy_binding=None)
    elif change == 'policy_expired':
        policy = dict(case['policy'], valid_until='2026-09-21T10:05:30+00:00')
        ref = dict(context.policy_binding)
        ref['sha256'] = _write(case['root']/ref['path'], policy)
        context = replace(context, policy_binding=ref)
    elif change == 'pending_reviews':
        ref = dict(path='runtime/TEST_ONLY-pending-reviews.json',
            sha256=_write(case['root']/'runtime/TEST_ONLY-pending-reviews.json', {'action':'no_order'}))
        context = replace(context, baseline_reviews_binding=ref)
    elif change == 'dict_context':
        context = {'approved': True, 'authorize_policy': True}
    elif change == 'bool_authorizer':
        context = replace(context, authorize_policy=True)
    else:
        calls = []
        def authorize(**kwargs):
            calls.append(True)
            if change == 'revoked_second_replay' and len(calls) >= 3:
                return False
            if len(calls) == 4:
                refs = json.loads((case['root']/case['binding_ref']['path']).read_bytes())
                paths = {'observation_last_auth': case['root']/refs['observation_ref']['path'],
                    'scan_last_auth': case['root']/refs['scan_ref']['path'],
                    'pointer_last_auth': case['pointer'], 'quote_last_auth': case['bundle'],
                    'approval_last_auth': case['root']/case['reviews_ref']['path'],
                    'policy_last_auth': case['root']/context.policy_binding['path']}
                path = paths[change]
                path.write_bytes(path.read_bytes()+b' ')
            return True
        context = replace(context, authorize_policy=authorize)
    result = execute(case, context=context)
    assert result['price_admitted'] is False, result
    assert result['price_comparison']['bridge_status'] != 'READY'
    assert result['compatibility']['comparison_eligible']['eligible'] is False
    assert result['formal_eligibility'] is False
    assert result['action'] == 'no_order'


@pytest.mark.parametrize('native_snapshot', [True], indirect=True)
def test_native_stale_keeps_its_status_in_actual_consumer(consumer):
    result = execute(consumer)
    assert result['current_snapshot_validity']['status'] == 'STALE'
    assert result['current_snapshot_validity']['model_validity']['status'] == 'STALE'
    assert result['price_admitted'] is False
    assert result['price_comparison']['bridge_status'] != 'READY'


def test_previous_china_day_snapshot_cannot_be_reused_by_consumer(consumer):
    result = execute(consumer, today=consumer['now']+timedelta(hours=14))
    assert result['price_admitted'] is False
    assert result['current_snapshot_validity']['status'] == 'UNKNOWN'
    # Native binding rejects yesterday's declared review window before the age check.
    assert 'Incremental binding identity/package/window mismatch' in result['reason']


@pytest.mark.parametrize('different_content', [False, True])
def test_independent_native_reader_cannot_mix_another_same_day_case(consumer, monkeypatch, different_content):
    """Isolate reader disagreement; all signed approval/Gate/source replay stays native."""
    case = consumer
    original = case['package_path'].read_bytes()
    other = case['root']/'runtime/TEST_ONLY-other-same-day-package.json'
    if different_content:
        payload = json.loads(original)
        payload['package_version'] = 'TEST_ONLY_DIFFERENT_SAME_DAY_VERSION'
        _write(other, payload)
    else:
        other.write_bytes(original)
    pointer = json.loads(case['pointer'].read_bytes())
    pointer['quotes']['600519'].update(research_package=other.relative_to(case['root']).as_posix(),
        research_package_sha256=sha256_file(other))
    _write(case['pointer'], pointer)
    # Explicit resolver-disagreement seam, not a substitute baseline approval.
    # Ordinary static X/Y pointers may already fail in the evaluator's policy check.
    def approved_package(root, symbol):
        _, payload = service.read_bound_json(root, case['package_ref'], 'TEST_ONLY approved Y')
        return dict(case['package_ref']), payload
    monkeypatch.setattr(service, 'registered_package', approved_package)
    result = execute(case)
    assert result['research_case']['package_path'] == other.relative_to(case['root']).as_posix()
    assert result['current_snapshot_validity']['bindings']['package'] == case['package_ref']
    assert result['price_admitted'] is False, result['status']
    assert result['price_comparison']['bridge_status'] != 'READY'


@pytest.mark.parametrize('field,value', [
    ('status', 'NOT_ADMITTED'), ('latest_completed_session', '2026-09-18'),
    ('source_evidence', []), ('collected_at', '2026-09-21T08:01:00+00:00')])
def test_late_quote_verdict_change_cannot_leave_ready(consumer, monkeypatch, field, value):
    from value_investment_agent.application.product import quote_bridge
    original = quote_bridge.admit_quote_for_research
    calls = []
    def admit(*args, **kwargs):
        path, digest, verdict = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 2:
            verdict = {**verdict, field: value}
        return path, digest, verdict
    monkeypatch.setattr(quote_bridge, 'admit_quote_for_research', admit)
    result = execute(consumer)
    assert len(calls) == 2
    assert result['price_admitted'] is False, result['status']
    assert result['price_comparison']['bridge_status'] != 'READY'


def test_case_date_projection_cannot_override_bound_package(consumer, monkeypatch):
    from value_investment_agent.application.product import quote_bridge
    original = quote_bridge._research_case_binding
    calls = []
    def case_binding(*args, **kwargs):
        case = original(*args, **kwargs)
        calls.append(True)
        return {**case, 'research_as_of': '2026-09-20'} if len(calls) == 1 else case
    monkeypatch.setattr(quote_bridge, '_research_case_binding', case_binding)
    result = execute(consumer)
    assert result['price_admitted'] is False
    assert 'research case dates or identity changed' in result['reason']


@pytest.mark.parametrize('role', ['original_case', 'pointer'])
def test_final_quote_read_cannot_hide_case_or_pointer_drift(consumer, monkeypatch, role):
    from value_investment_agent.application.product import quote_bridge
    original = quote_bridge.admit_quote_for_research
    calls = []
    def admit(*args, **kwargs):
        admitted = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 2:
            path = consumer['package_path'] if role == 'original_case' else consumer['pointer']
            path.write_bytes(path.read_bytes()+b' ')
        return admitted
    monkeypatch.setattr(quote_bridge, 'admit_quote_for_research', admit)
    result = execute(consumer)
    assert len(calls) == 2
    assert result['price_admitted'] is False
    assert result['price_comparison']['bridge_status'] != 'READY'


def test_b1_next_day_acquisition_does_not_gain_snapshot_permission(consumer, monkeypatch):
    from value_investment_agent import disclosures
    from value_investment_agent.application.product import daily_event_observation as daily
    case = consumer
    case['now'] = datetime(2026, 9, 22, 0, 6, tzinfo=timezone.utc)
    acquired = case['now']-timedelta(minutes=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return acquired.astimezone(tz) if tz else acquired.replace(tzinfo=None)
    monkeypatch.setattr(daily, 'datetime', Clock)
    old_scan = json.loads((case['root']/json.loads(
        (case['root']/case['binding_ref']['path']).read_bytes())['scan_ref']['path']).read_bytes())
    filing = old_scan['announcements'][0]
    def request(parameters, *, raw_response_sink):
        rows = [dict(secCode='600519', orgId='TEST_ONLY_native',
            announcementId=filing['announcement_id'], announcementTitle=filing['title'],
            adjunctUrl='finalpage/2026-09-21/9000000001.PDF',
            announcementTime=int(datetime.fromisoformat(filing['published_at']).timestamp()*1000))]
        payload = dict(totalAnnouncement=1, announcements=rows, hasMore=False)
        if not parameters['seDate']:
            payload = dict(totalAnnouncement=1, announcements=[dict(secCode='600519', orgId='TEST_ONLY_native')])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method='POST', request=parameters,
            page=int(parameters['pageNum']), acquired_at=acquired.isoformat(),
            sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body)))
        return payload
    monkeypatch.setattr(disclosures, '_request_json', request)
    observation = daily.collect_daily_event_observation(root=case['root'], symbol='600519',
        issuer_name='TEST_ONLY', start=date(2026,9,21), end=date(2026,9,22),
        output_dir=case['root']/'runtime/TEST_ONLY-next-morning', retain_raw_index=True)
    binding = json.loads((case['root']/case['binding_ref']['path']).read_bytes())
    binding.update(review_cutoff='2026-09-22', scan_ref=observation['scan_binding'],
        observation_ref=dict(path='runtime/TEST_ONLY-next-morning/observation.json',
            sha256=sha256_file(case['root']/'runtime/TEST_ONLY-next-morning/observation.json')))
    binding_ref = dict(path='runtime/TEST_ONLY-next-morning/binding.json',
        sha256=_write(case['root']/'runtime/TEST_ONLY-next-morning/binding.json', binding))
    policy = dict(case['policy'], valid_until='2026-09-22T01:00:00+00:00')
    policy_ref = dict(case['context'].policy_binding)
    policy_ref['sha256'] = _write(case['root']/policy_ref['path'], policy)
    case['context'] = replace(case['context'], policy_binding=policy_ref)
    bundle = json.loads(case['bundle'].read_bytes())
    documents, identities = {}, {}
    for key, value in bundle['documents'].items():
        value = dict(value, fetched_at='2026-09-22T00:00:00+00:00')
        identity = hashlib.sha256((value['source_url']+'\n'+value['fetched_at']+'\n'+value['sha256']).encode()).hexdigest()
        documents[identity], identities[key] = value, identity
    bundle['documents'] = documents
    refs = bundle['references']['600519']['document_refs']
    for key, value in refs.items():
        refs[key] = [identities[item] for item in value] if isinstance(value,list) else identities[value]
    bundle['finished_at'] = '2026-09-22T00:00:00+00:00'
    digest = _write(case['bundle'], bundle)
    pointer = json.loads(case['pointer'].read_bytes())
    pointer['quotes']['600519']['quote_bundle_sha256'] = digest
    pointer['quotes']['600519']['incremental_validity_binding'] = binding_ref
    _write(case['pointer'], pointer)
    result = execute(case)
    assert result['current_snapshot_validity']['usable_for_research_comparison'] is True, result['reason']
    assert result['quote_verification_status'] == 'HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY'
    assert result['price_admitted'] is False
    assert result['price_comparison']['bridge_status'] != 'READY'
    assert 'B1 requires same-session post-close acquisition' in result['reason']
