"""Native signed/G3/Gate and raw-page/PDF E2E plus focused seam negatives.

All economic inputs, keys, identities and clocks are TEST_ONLY, never production.
"""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from test_incremental_validity import _partial_v2, _write
from test_pending_review_response import signed, consume, whole_approval
from test_d2_conditional_shared_service import synthetic_chain
from value_investment_agent.application.product import current_snapshot_validity as service
from value_investment_agent.application.product.incremental_validity import (
    resolve_current_snapshot_validity, resolve_incremental_model_validity,
)
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_bridge import bridge_with_quote
from value_investment_agent.quote_snapshot import QuoteSnapshot, QUOTE_STATUS_VERIFIED_CLOSE
from value_investment_agent.valuation_models.base import ValuationResult
from value_investment_agent.research_run_contract import valuation_result_sha256


@pytest.fixture
def snapshot(tmp_path, monkeypatch, request):
    ref, binding, package, _ = _partial_v2(tmp_path, monkeypatch, populated=getattr(request, 'param', False))
    now = datetime(2020, 1, 2, 10, tzinfo=timezone.utc)
    valuation = ValuationResult('600519', 'TEST_ONLY', date(2020, 1, 1),
        Decimal('20'), Decimal('30'), Decimal('40'), '\u4e2d', {}, [],
        [{'id': 'TEST_ONLY_BASELINE'}], [], 'approved_research_only', 'TEST_ONLY')
    validity = ModelValidity('TEST_ONLY', '600519', date(2020, 1, 1), date(2020, 1, 1),
        date(2020, 1, 1), False, False, False, 'VALID', [], [{'id': 'TEST_ONLY_BASELINE'}])
    baseline = service.ApprovedBaseline(valuation, validity, now-timedelta(hours=2),
        'TEST_ONLY_EXISTING_APPROVAL', 'TEST_ONLY_RULE_V1', 'TEST_ONLY_RESEARCH_V1',
        {'transport': 'TEST_ONLY_TRUSTED_REPLAY_SEAM'}, ())
    reviews = {'path': 'runtime/TEST_ONLY-reviews.json',
               'sha256': _write(tmp_path/'runtime/TEST_ONLY-reviews.json', {'TEST_ONLY': True})}
    policy = dict(schema_version=service.POLICY_SCHEMA, scope=service.SCOPE,
        action='no_order', symbol='600519', rule='ZERO_NEW_OR_CHANGED_FILINGS',
        baseline_package=binding['package_ref'], baseline_reviews=reviews,
        approval_id=baseline.approval_id, approval_transport=baseline.approval_transport,
        approval_set=baseline.approval_set,
        valuation_sha256=valuation_result_sha256(valuation),
        model_id='TEST_ONLY', model_version='TEST_ONLY', rule_version=baseline.rule_version,
        research_version=baseline.research_version, max_snapshot_age_seconds=600,
        valid_from=(now-timedelta(hours=3)).isoformat(), valid_until=(now+timedelta(hours=1)).isoformat(),
        confirmed_at=(now-timedelta(hours=1)).isoformat())
    policy_ref = {'path': 'runtime/TEST_ONLY-policy.json',
                  'sha256': _write(tmp_path/'runtime/TEST_ONLY-policy.json', policy)}
    calls = []
    def replay(root, package, reviews_ref, at):
        calls.append(at)
        return baseline
    monkeypatch.setattr(service, '_replay_approved_baseline', replay)
    args = dict(root=tmp_path, symbol='600519', incremental_binding_ref=ref,
        baseline_reviews_binding=reviews, policy_binding=policy_ref, now=now,
        authorize_policy=lambda **kwargs: True)  # Trusted TEST_ONLY app dependency.
    return dict(args=args, baseline=baseline, binding=binding, package=package,
                policy=policy, calls=calls)


def evaluate(snapshot, **overrides):
    return resolve_current_snapshot_validity(**dict(snapshot['args'], **overrides))


def reseal(snapshot, key, payload):
    ref = snapshot['args'][key]
    ref['sha256'] = _write(snapshot['args']['root']/ref['path'], payload)


def test_native_snapshot_reaches_scoped_shared_bridge_without_upgrading_legacy(snapshot):
    args = snapshot['args']
    before = snapshot['package'].read_bytes()
    result = evaluate(snapshot)
    assert result.usable_for_research_comparison, result.blockers
    assert len(snapshot['calls']) == 2
    assert result.valuation == snapshot['baseline'].valuation
    assert result.valuation.valuation_date == date(2020, 1, 1)
    quote = QuoteSnapshot('600519', date(2020, 1, 2), Decimal('18'), QUOTE_STATUS_VERIFIED_CLOSE,
                          [{'id': 'TEST_ONLY_QUOTE', 'sha256': 'a'*64}])
    comparison = bridge_with_quote(result.valuation, result.model_validity, quote)
    assert comparison.bridge_status == 'READY'
    assert comparison.margin_to_base == Decimal('0.4')
    envelope = result.as_policy()
    assert envelope['scope'] == service.SCOPE
    assert envelope['knowledge_as_of'] == args['now'].isoformat()
    for flag in ('full_calendar_window_elapsed', 'formal_eligibility',
                 'g3_approval_granted', 'strategy_approval_granted', 'research_cutoff_changed'):
        assert envelope[flag] is False
    assert envelope['action'] == 'no_order'
    json.dumps(envelope, allow_nan=False)
    assert snapshot['package'].read_bytes() == before
    legacy = resolve_incremental_model_validity(root=args['root'], symbol='600519',
        binding_ref=args['incremental_binding_ref'], review_cutoff=date(2020, 1, 2), today=args['now'])
    assert legacy.status == 'UNKNOWN'
    assert 'INTRADAY_SNAPSHOT_NOT_FULL_WINDOW' in legacy.blockers


@pytest.mark.parametrize('change', ['missing_policy', 'missing_authorizer', 'denied', 'expired',
    'stale_snapshot', 'ttl_missing', 'ttl_bool', 'midnight', 'naive', 'future',
    'model', 'package', 'approval', 'rule', 'research', 'transport', 'approval_set', 'valuation', 'policy_hash', 'reviews_hash'])
def test_policy_clock_and_identity_fail_closed(snapshot, change):
    args, policy = snapshot['args'], snapshot['policy']
    overrides = {}
    if change == 'missing_policy': overrides['policy_binding'] = None
    elif change == 'missing_authorizer': overrides['authorize_policy'] = None
    elif change == 'denied': overrides['authorize_policy'] = lambda **kwargs: False
    elif change == 'expired': policy['valid_until'] = (args['now']-timedelta(seconds=1)).isoformat()
    elif change == 'stale_snapshot': overrides['now'] = args['now']+timedelta(minutes=11)
    elif change == 'ttl_missing': policy.pop('max_snapshot_age_seconds')
    elif change == 'ttl_bool': policy['max_snapshot_age_seconds'] = True
    elif change == 'midnight': overrides['now'] = args['now'].replace(hour=16)
    elif change == 'naive': overrides['now'] = args['now'].replace(tzinfo=None)
    elif change == 'future': overrides['now'] = args['now']-timedelta(seconds=1)
    elif change == 'model': policy['model_id'] = 'other'
    elif change == 'package': policy['baseline_package'] = dict(policy['baseline_package'], sha256='0'*64)
    elif change == 'approval': policy['approval_id'] = 'other'
    elif change == 'rule': policy['rule_version'] = 'other'
    elif change == 'research': policy['research_version'] = 'other'
    elif change == 'transport': policy['approval_transport'] = {'transport': 'FAKE'}
    elif change == 'approval_set': policy['approval_set'] = {'g3_only': 'TEST_ONLY_OMISSION'}
    elif change == 'valuation': policy['valuation_sha256'] = '0'*64
    elif change == 'policy_hash': args['policy_binding']['sha256'] = '0'*64
    elif change == 'reviews_hash': args['baseline_reviews_binding']['sha256'] = '0'*64
    if change not in {'policy_hash', 'reviews_hash'}:
        reseal(snapshot, 'policy_binding', policy)
    result = evaluate(snapshot, **overrides)
    assert not result.usable_for_research_comparison
    assert result.status == 'UNKNOWN'
    assert result.blockers
    assert result.as_policy()['formal_eligibility'] is False


@pytest.mark.parametrize('change', ['pending', 'revoked', 'low', 'stale', 'damaged', 'late_approval'])
def test_baseline_never_inherits_new_approval(snapshot, monkeypatch, change):
    baseline = snapshot['baseline']
    if change in {'pending', 'revoked'}:
        def replay(*args): raise ValueError('TEST_ONLY baseline ' + change)
    else:
        if change == 'low': baseline = replace(baseline, valuation=replace(baseline.valuation, confidence='\u4f4e'))
        elif change == 'stale': baseline = replace(baseline, validity=replace(baseline.validity,
            status='STALE', material_event_found=True))
        elif change == 'damaged': baseline = replace(baseline, validity=replace(baseline.validity,
            status='UNKNOWN', material_event_found=None, blockers=['TEST_ONLY_ORIGINAL_UNRESOLVED']))
        elif change == 'late_approval': baseline = replace(baseline, reviewed_at=snapshot['args']['now']+timedelta(seconds=1))
        def replay(*args): return baseline
    monkeypatch.setattr(service, '_replay_approved_baseline', replay)
    result = evaluate(snapshot)
    assert result.status == ('STALE' if change == 'stale' else 'UNKNOWN')
    assert not result.usable_for_research_comparison
    if change == 'stale': assert result.model_validity.material_event_found is True


@pytest.mark.parametrize('during', [False, True])
def test_final_source_and_authority_recheck(snapshot, during):
    args = snapshot['args']
    raw = next((args['root']/'runtime/events/raw-index').glob('*.bin'))
    if not during:
        raw.write_bytes(b'TEST_ONLY_DRIFT')
    else:
        def authorize(**kwargs):
            raw.write_bytes(b'TEST_ONLY_DRIFT_DURING_EVALUATION')
            return True
        args['authorize_policy'] = authorize
    assert not evaluate(snapshot).usable_for_research_comparison


def test_policy_revoked_on_final_check(snapshot):
    calls = []
    def authorize(**kwargs):
        calls.append(True)
        return len(calls) == 1
    result = evaluate(snapshot, authorize_policy=authorize)
    assert not result.usable_for_research_comparison
    assert len(calls) == 2


@pytest.mark.parametrize('change', ['new', 'old_late', 'same_id_hash', 'missing'])
def test_new_changed_and_backfilled_filings_are_not_price_reuse(snapshot, monkeypatch, change):
    from value_investment_agent.event_scan import AnnouncementReview
    item = AnnouncementReview('999', datetime(2020, 1, 1, tzinfo=timezone.utc),
        'TEST_ONLY', 'https://example.test/999.pdf', 'unknown', 'PENDING_HUMAN_REVIEW',
        True, False, ({'id': 'TEST_ONLY', 'sha256': 'b'*64},))
    baseline = snapshot['baseline']
    if change == 'same_id_hash':
        monkeypatch.setattr(service, '_announcement_map', lambda items:
            {'999': 'OLD_HASH' if items else 'NEW_HASH'})
        baseline = replace(baseline, announcements=(item,))
    elif change == 'missing': baseline = replace(baseline, announcements=(item,))
    else:
        # Inject only the parsed announcement sequence after native raw replay;
        # native replays remain real, while this isolates the NEW-set predicate.
        parse = service.event_scan_from_payload
        def parsed(payload):
            scan = parse(payload)
            return replace(scan, announcements=(replace(item, published_at=(
                    datetime(2020, 1, 1, 1, tzinfo=timezone.utc) if change == 'old_late'
                else snapshot['args']['now'])),))
        monkeypatch.setattr(service, 'event_scan_from_payload', parsed)
    monkeypatch.setattr(service, '_replay_approved_baseline', lambda *args: baseline)
    result = evaluate(snapshot)
    assert not result.usable_for_research_comparison
    assert any('FILINGS' in blocker for blocker in result.blockers)


def test_default_native_baseline_rejects_unapproved_input(snapshot, monkeypatch):
    # No approval identity or signature is generated by this feature/test.
    monkeypatch.undo()
    result = evaluate(snapshot)
    assert not result.usable_for_research_comparison
    assert result.status == 'UNKNOWN'


@pytest.mark.parametrize('snapshot', [True], indirect=True)
@pytest.mark.parametrize('change', ['new', 'same_id_changed_hash'])
def test_native_received_pdf_and_page_replay_cannot_skip_nonzero_events(snapshot, monkeypatch, change):
    args = snapshot['args']
    path = args['root']/snapshot['binding']['scan_ref']['path']
    scan = service.event_scan_from_payload(json.loads(path.read_bytes()))
    assert len(scan.announcements) > 0
    if change == 'same_id_changed_hash':
        first = scan.announcements[0]
        refs = tuple(dict(ref, sha256='0'*64) for ref in first.evidence_refs)
        baseline = replace(snapshot['baseline'], announcements=(replace(first, evidence_refs=refs),))
        monkeypatch.setattr(service, '_replay_approved_baseline', lambda *args: baseline)
    result = evaluate(snapshot)
    assert not result.usable_for_research_comparison
    assert result.blockers == ('NEW_CHANGED_OR_MISSING_FILINGS_REQUIRE_REVIEW',)


def test_known_stale_is_not_erased_by_missing_policy(snapshot, monkeypatch):
    baseline = snapshot['baseline']
    baseline = replace(baseline, validity=replace(baseline.validity,
        status='STALE', material_event_found=True))
    monkeypatch.setattr(service, '_replay_approved_baseline', lambda *args: baseline)
    result = evaluate(snapshot, policy_binding=None)
    assert result.status == 'STALE'
    assert result.model_validity.material_event_found is True


@pytest.mark.parametrize('change', ['baseline', 'pointer', 'source_on_last_auth', 'reviews'])
def test_last_revalidation_rejects_concurrent_drift(snapshot, monkeypatch, change):
    calls = []
    args = snapshot['args']
    def authorize(**kwargs):
        calls.append(True)
        if len(calls) == 2:
            if change == 'pointer':
                pointer = args['root']/'config/current-quote-bridge.json'
                pointer.write_bytes(pointer.read_bytes()+b' ')
            elif change == 'source_on_last_auth':
                next((args['root']/'runtime/events/raw-index').glob('*.bin')).write_bytes(b'TEST_ONLY_FINAL_DRIFT')
            elif change == 'reviews':
                (args['root']/args['baseline_reviews_binding']['path']).write_bytes(b'TEST_ONLY_FINAL_DRIFT')
        return True
    if change == 'baseline':
        replay_calls = []
        def replay(*args):
            replay_calls.append(True)
            baseline = snapshot['baseline']
            return baseline if len(replay_calls) == 1 else replace(baseline, approval_id='TEST_ONLY_REVOKED')
        monkeypatch.setattr(service, '_replay_approved_baseline', replay)
    result = evaluate(snapshot, authorize_policy=authorize)
    assert not result.usable_for_research_comparison
    assert result.status == 'UNKNOWN'


@pytest.mark.parametrize('expired', [False, True])
def test_native_authenticated_g3_does_not_upgrade_pending_or_expired_baseline(signed, expired):
    from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
    signed['response']['whole_model_approval'] = whole_approval(signed)
    receipt = consume(signed)
    root = signed['root']
    package = json.loads((signed['path'].parent/'package.json').read_bytes())
    now = datetime.now(timezone.utc) + (timedelta(days=2) if expired else timedelta())
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError, match=('BASELINE_APPROVAL_AUTHORITY_EXPIRED'
                if expired else 'BASELINE_RESEARCH_NOT_APPROVED')):
            service._replay_approved_baseline(root, package, receipt['review_packet_binding'], now)


@pytest.fixture
def native_snapshot(synthetic_chain, monkeypatch, request):
    """Native signed/event/G3/Gate baseline, native partial pages/PDF; economics TEST_ONLY."""
    from hashlib import sha256
    from pypdf import PdfWriter
    from test_p7_signed_review_workflow import _complete_signed_case
    from value_investment_agent import disclosures
    from value_investment_agent.application.product import daily_event_observation as daily
    from value_investment_agent.event_scan import event_scan_from_payload

    root, source, *rest = synthetic_chain
    chain = list(synthetic_chain)
    package = json.loads(source.read_bytes())
    raw_source = root/'runtime/TEST_ONLY-baseline-financial-original.json'
    _write(raw_source, {'TEST_ONLY': 'economic inputs are fixtures, never issuer evidence'})
    for item in package['sources']:
        item.update(local_path=raw_source.relative_to(root).as_posix(), sha256=sha256_file(raw_source))
    for evidence in package['facts']['evidence_refs']:
        if evidence['id'] == 'f-1':
            evidence['sha256'] = sha256_file(raw_source)
    package['rule_version'] = 'TEST_ONLY_SNAPSHOT_BASELINE_RULE'
    pdf = root/'runtime/TEST_ONLY-approved-filing.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf.open('wb') as stream: writer.write(stream)
    scan_path = root/'synthetic-scan.json'
    original_scan = event_scan_from_payload(json.loads(scan_path.read_bytes()))
    item = original_scan.announcements[0]
    url = 'https://static.cninfo.com.cn/finalpage/2026-09-21/9000000001.PDF'
    ref = dict(id='synthetic-disclosure', path=pdf.relative_to(root).as_posix(),
               sha256=sha256_file(pdf), source_url=url)
    scan = replace(original_scan, evidence_refs=(ref,), announcements=(
        replace(item, source_url=url, evidence_refs=(ref,)),))
    scan_sha = _write(scan_path, scan.as_policy())
    package['model_validity_input']['event_scan_ref']['sha256'] = scan_sha
    _write(source, package)
    chain[6] = replace(chain[6], scan_sha256=scan_sha, decisions=tuple(
        replace(decision, source_ref={k:v for k,v in ref.items() if k != 'sha256'},
                source_sha256=ref['sha256']) for decision in chain[6].decisions))
    chain[7] = scan_sha
    stale = getattr(request, 'param', False)
    if stale:
        chain[6] = replace(chain[6], decisions=tuple(replace(decision,
            human_decision='MATERIAL_REQUIRES_RECALCULATION', requires_model_stale=True,
            requires_recalculation=True) for decision in chain[6].decisions))
    # Recompile only the TEST_ONLY economics after binding its original bytes;
    # the following helper still performs all native signing/import/G3 checks.
    from value_investment_agent.m1_valuation_package_builder import build_descriptor
    from value_investment_agent.research_input import build_research_run_spec
    from value_investment_agent.research_application import ResearchApplicationService
    from value_investment_agent.human_research_approval import artifact_fingerprint
    descriptor = build_descriptor(package, root=root)
    calculated = ResearchApplicationService().run_company_research(build_research_run_spec(descriptor))
    exact = descriptor.as_policy()
    chain[5] = replace(chain[5], valuation_artifact_sha256=valuation_result_sha256(calculated.valuation),
        research_case_sha256=artifact_fingerprint(exact['research_case']),
        facts_artifact_sha256=artifact_fingerprint(exact['facts']),
        assumption_set_sha256=artifact_fingerprint(exact['assumptions']))
    restored, _, _ = _complete_signed_case(tuple(chain), monkeypatch, price_eligible=not stale)
    assert restored.dependency_objects['model_validity'].status == ('STALE' if stale else 'VALID')
    assert restored.dependency_objects['human_approval'].verified_transport is not None
    now = datetime(2026, 9, 21, 10, 6, tzinfo=timezone.utc)
    acquired = now-timedelta(minutes=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return acquired.astimezone(tz) if tz else acquired.replace(tzinfo=None)
    monkeypatch.setattr(daily, 'datetime', Clock)
    def request(parameters, *, raw_response_sink):
        rows = [dict(secCode='600519', orgId='TEST_ONLY_native', announcementId=item.announcement_id,
            announcementTitle=item.title, adjunctUrl='finalpage/2026-09-21/9000000001.PDF',
            announcementTime=int(item.published_at.timestamp()*1000))]
        payload = dict(totalAnnouncement=1, announcements=rows, hasMore=False)
        if not parameters['seDate']:
            payload = dict(totalAnnouncement=1, announcements=[dict(secCode='600519', orgId='TEST_ONLY_native')])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method='POST', request=parameters,
            page=int(parameters['pageNum']), acquired_at=acquired.isoformat(),
            sha256=sha256(body).hexdigest(), size_bytes=len(body)))
        return payload
    monkeypatch.setattr(disclosures, '_request_json', request)
    def download(url, path):
        path.write_bytes(pdf.read_bytes())
        return sha256_file(path)
    monkeypatch.setattr(daily, 'download_disclosure_pdf', download)
    observation = daily.collect_daily_event_observation(root=root, symbol='600519', issuer_name='TEST_ONLY',
        start=date(2026,9,21), end=date(2026,9,21), output_dir=root/'runtime/native-partial', retain_raw_index=True)
    package_path = root/'runtime/TEST_ONLY-signing/package.json'
    package_ref = dict(path=package_path.relative_to(root).as_posix(), sha256=sha256_file(package_path))
    _write(root/'config/current-quote-bridge.json', dict(schema_version='current-quote-bridge-v1',
        action='no_order', quotes={'600519':dict(research_package=package_ref['path'],
            research_package_sha256=package_ref['sha256'])}))
    binding = dict(schema_version='incremental-validity-binding-v2', symbol='600519', action='no_order',
        package_ref=package_ref, research_as_of='2026-09-21', valuation_date='2026-09-21',
        model_valid_from='2026-09-21', scan_from='2026-09-21', review_cutoff='2026-09-21',
        model_id=package['model_validity_input']['model_id'], materiality_approved=False,
        g3_approval_granted=False, research_cutoff_changed=False, coverage_mode='PARTIAL_INTRADAY_SNAPSHOT',
        scan_ref=observation['scan_binding'], observation_ref=dict(path='runtime/native-partial/observation.json',
            sha256=sha256_file(root/'runtime/native-partial/observation.json')))
    binding_ref = dict(path='runtime/native-partial/binding.json', sha256=_write(root/'runtime/native-partial/binding.json',binding))
    reviews_path=root/'runtime/TEST_ONLY-signing/complete-reviews.json'
    reviews_ref=dict(path=reviews_path.relative_to(root).as_posix(),sha256=sha256_file(reviews_path))
    return dict(root=root,now=now,package_path=package_path,package_ref=package_ref,
        reviews_ref=reviews_ref,binding_ref=binding_ref,observation=observation,restored=restored)


def test_native_signed_baseline_and_native_partial_reach_scoped_ready(native_snapshot):
    from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
    case=native_snapshot
    with _use_test_trust_registry(case['root']/'TEST_ONLY-combined-trust-registry.json'):
        baseline=service._replay_approved_baseline(case['root'],json.loads(case['package_path'].read_bytes()),
            case['reviews_ref'],case['now'])
        policy=dict(schema_version=service.POLICY_SCHEMA,scope=service.SCOPE,action='no_order',symbol='600519',
            rule='ZERO_NEW_OR_CHANGED_FILINGS',baseline_package=case['package_ref'],baseline_reviews=case['reviews_ref'],
            approval_id=baseline.approval_id,approval_transport=baseline.approval_transport,
            approval_set=baseline.approval_set,
            model_id=baseline.validity.model_id,model_version=baseline.valuation.model_version,
            rule_version=baseline.rule_version,research_version=baseline.research_version,
            valuation_sha256=valuation_result_sha256(baseline.valuation),max_snapshot_age_seconds=600,
            valid_from='2026-09-21T10:00:00+00:00',valid_until='2026-09-21T11:00:00+00:00',
            confirmed_at='2026-09-21T10:01:00+00:00')
        ref=dict(path='runtime/TEST_ONLY-native-snapshot-policy.json',
            sha256=_write(case['root']/'runtime/TEST_ONLY-native-snapshot-policy.json',policy))
        result=resolve_current_snapshot_validity(root=case['root'],symbol='600519',
            incremental_binding_ref=case['binding_ref'],baseline_reviews_binding=case['reviews_ref'],
            policy_binding=ref,now=case['now'],authorize_policy=lambda **kwargs:True)
    assert result.usable_for_research_comparison,result.blockers
    quote=QuoteSnapshot('600519',date(2026,9,21),Decimal('5'),QUOTE_STATUS_VERIFIED_CLOSE,
        [{'id':'TEST_ONLY_NATIVE_QUOTE','sha256':'a'*64}])
    assert bridge_with_quote(result.valuation,result.model_validity,quote).bridge_status=='READY'
    assert result.as_policy()['formal_eligibility'] is False
    assert result.knowledge_as_of == case['now']
    assert result.observed_at == case['now']-timedelta(minutes=1)
    assert baseline.available_at == case['now']
    assert result.bindings['approval_set']['materiality']
    assert result.bindings['approval_set']['g3_completion']
    assert result.valuation == case['restored'].dependency_objects['valuation']


@pytest.mark.parametrize('native_snapshot', [True], indirect=True)
@pytest.mark.parametrize('expired', [False, True])
def test_native_known_stale_survives_price_denial_expiry_and_missing_policy(native_snapshot, expired):
    from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
    case = native_snapshot
    now = case['now']+(timedelta(days=2) if expired else timedelta())
    with _use_test_trust_registry(case['root']/'TEST_ONLY-combined-trust-registry.json'):
        baseline = service._replay_approved_baseline(case['root'], json.loads(case['package_path'].read_bytes()),
            case['reviews_ref'], now)
        assert baseline.validity.status == 'STALE'
        assert any('NOT_APPROVED' in blocker for blocker in baseline.blockers)
        result = resolve_current_snapshot_validity(root=case['root'], symbol='600519',
            incremental_binding_ref=case['binding_ref'], baseline_reviews_binding=case['reviews_ref'],
            policy_binding=None, now=now)
    assert result.status == 'STALE'
    assert result.model_validity.material_event_found is True
    assert not result.usable_for_research_comparison


def test_native_materiality_set_cannot_be_stripped_while_retaining_g3(native_snapshot):
    from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
    case = native_snapshot
    packet = json.loads((case['root']/case['reviews_ref']['path']).read_bytes())
    del packet['bindings']['event_materiality']
    del packet['authenticated_materiality_binding']
    packet['schema_version'] = 'shared-research-review-inputs-v1'
    ref = dict(path='runtime/TEST_ONLY-shrunken-packet.json',
        sha256=_write(case['root']/'runtime/TEST_ONLY-shrunken-packet.json', packet))
    with _use_test_trust_registry(case['root']/'TEST_ONLY-combined-trust-registry.json'):
        with pytest.raises(ValueError, match='APPROVAL_SET_SHRANK'):
            service._replay_approved_baseline(case['root'], json.loads(case['package_path'].read_bytes()),
                ref, case['now'])


def test_final_policy_read_is_a_real_bound_read(snapshot, monkeypatch):
    read = service.read_bound_json
    called = []
    def drift(root, ref, label):
        if label == 'snapshot policy final read':
            called.append(True)
            (root/ref['path']).write_bytes(b'TEST_ONLY_FINAL_POLICY_DRIFT')
        return read(root, ref, label)
    monkeypatch.setattr(service, 'read_bound_json', drift)
    result = evaluate(snapshot)
    assert called == [True]
    assert not result.usable_for_research_comparison


def test_availability_upper_bound_does_not_refresh_an_old_query(snapshot, monkeypatch):
    now = snapshot['args']['now']+timedelta(minutes=11)
    baseline = replace(snapshot['baseline'], available_at=now)
    monkeypatch.setattr(service, '_replay_approved_baseline', lambda *args: baseline)
    result = evaluate(snapshot, now=now)
    assert result.knowledge_as_of == now
    assert result.observed_at == snapshot['args']['now']
    assert not result.usable_for_research_comparison
    assert any('FRESHNESS_EXPIRED' in blocker for blocker in result.blockers)


def test_native_baseline_computation_date_drift_breaks_signed_context(native_snapshot):
    from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
    case = native_snapshot
    package = json.loads(case['package_path'].read_bytes())
    package['point_in_time']['computed_at'] = (case['now']+timedelta(seconds=1)).isoformat()
    with _use_test_trust_registry(case['root']/'TEST_ONLY-combined-trust-registry.json'):
        # The native signed model context rejects this mutation before availability checks.
        with pytest.raises(ValueError, match='materiality artifact model context missing, unknown or mismatched'):
            service._replay_approved_baseline(case['root'], package, case['reviews_ref'], case['now'])


@pytest.mark.parametrize('role', ['observation_ref', 'scan_ref'])
def test_last_policy_callback_cannot_change_query_json(snapshot, role):
    calls = []
    ref = snapshot['binding'][role]
    path = snapshot['args']['root']/ref['path']
    before = path.read_bytes()
    def authorize(**kwargs):
        calls.append(True)
        if len(calls) == 2:
            path.write_bytes(before+b' ')  # Semantic JSON unchanged, exact bytes drift.
        return True
    result = evaluate(snapshot, authorize_policy=authorize)
    assert len(calls) == 2
    assert not result.usable_for_research_comparison
    assert result.status == 'UNKNOWN'
    assert any('snapshot final input hash mismatch' in blocker for blocker in result.blockers)
    assert result.as_policy()['formal_eligibility'] is False
