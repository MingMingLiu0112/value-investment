"""TEST_ONLY raw HTTP replay + trusted-baseline seam; no production approval.

The positive seam represents an already authenticated baseline; it does NOT test
signature minting. Separate negatives exercise the default native baseline loader.
"""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from test_incremental_validity import _partial_v2, _write
from test_pending_review_response import signed, consume, whole_approval
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
    'model', 'package', 'approval', 'rule', 'research', 'transport', 'valuation', 'policy_hash', 'reviews_hash'])
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
