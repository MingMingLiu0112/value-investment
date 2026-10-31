"""TEST_ONLY source-bound read projections; never genuine forward/Shadow records."""
from copy import deepcopy
from datetime import timezone, timedelta
import hashlib
import json
from uuid import uuid4

import pytest

from test_current_price_registry import register
from test_hotspot_current_price_case import NOW as BOUND_AT
from test_hotspot_forward_research import fresh_bundle, capture, OBSERVE
from test_public_observation_session import files
from value_investment_agent.application.hotspot.current_registry import load_price_conditions
from value_investment_agent.application.hotspot.intraday_plan_observation import bind_quote_plan
from value_investment_agent.application.hotspot import public_observation_session as service


def fixture(root, *, observed_at=OBSERVE, bound_at=BOUND_AT):
    prior = register(root)
    plan = load_price_conditions(root, now=BOUND_AT, research_version='TEST_ONLY')['items'][0]['price_action_plan']
    binding = bind_quote_plan(plan, symbol='600519', now=bound_at)
    original_bundle = json.loads((root / prior['current_reference_close']['bundle_path']).read_bytes())
    bundle = fresh_bundle(original_bundle, observed_at)
    path = root / 'runtime/TEST_ONLY-next-session.json'
    path.write_text(json.dumps(bundle), encoding='utf-8')
    current = capture(root=root, symbol='600519', as_of=observed_at.date(),
        quote_bundle_path=path, quote_bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), now=observed_at)
    pointer = root / 'config/current-price-conditions.json'
    registry = json.loads(pointer.read_bytes())
    registry['items'][0].update(case_path=current['case_path'], case_sha256=current['case_sha256'])
    pointer.write_text(json.dumps(registry), encoding='utf-8')
    report = dict(schema_version=service.COMPLETED_PLAN_SCHEMA, namespace='TEST_ONLY',
        status='STOPPED', detail='TEST_ONLY_NO_WORKER', symbol='600519',
        session_id=str(uuid4()), samples=[], bindings=[], plan_binding=binding)
    return report, prior, current


def project(root, report, at=OBSERVE):
    return service._sealed_condition_path(root, report, now=at)


def test_native_read_projection_has_no_network_writes_or_audit_changes(tmp_path):
    report, prior, current = fixture(tmp_path)
    session = service.PublicObservationSession(tmp_path, clock=lambda: OBSERVE,
        collector=lambda symbols: pytest.fail('Read cannot collect'),
        bar_collector=lambda symbol: pytest.fail('Read cannot collect bars'))
    session.directory.mkdir(parents=True)
    session._current = deepcopy(report)
    session._persist()  # TEST_ONLY fixture storage, not a worker or production run.
    before = files(tmp_path)
    result = session.read()
    review = result['sealed_condition_path']
    assert review['status'] == 'NOT_TRIGGERED'
    assert review['scope'] == 'SOURCE_BOUND_PLAN_RECONSTRUCTION'
    assert review['bound_at'] == report['plan_binding']['bound_at']
    assert review['prior_case_binding']['sha256'] == prior['case_sha256']
    assert review['current_case_binding']['sha256'] == current['case_sha256']
    assert review['original_condition']['entry_trigger_price'] == '13'
    assert review['original_condition']['invalidation_price'] == '11'
    assert review['actual_shadow_sessions'] == 0
    assert review['strict_pit_admitted'] is review['formal_eligibility'] is False
    assert result['status'] == 'STOPPED' and result['monitor_running'] is False
    assert result['completed_plan_observation'] is None
    assert result['plan_binding'] == report['plan_binding']
    assert files(tmp_path) == before
    assert all('sealed_condition_path' not in json.loads(path.read_bytes())
               for path in session.directory.glob('*.report.json'))
    session._current = None
    assert session.read() == result


def test_no_binding_cannot_use_available_at_or_eight_sampled_bars(tmp_path):
    report = dict(symbol='600519', samples=[dict(document={'60m': [{}] * 8},
                                               data_available_at=BOUND_AT.isoformat())])
    before = files(tmp_path)
    result = project(tmp_path, report)
    assert result['status'] == 'UNASSESSABLE'
    assert result['reason'] == 'NO_PERSISTED_PRIOR_PLAN_BINDING'
    assert files(tmp_path) == before


@pytest.mark.parametrize('defect', ['binding_hash', 'changed_rule_price', 'prior_source',
                                   'current_source', 'duplicate', 'missing_registry'])
def test_corrupt_or_nonunique_sources_fail_closed(tmp_path, defect):
    report, prior, current = fixture(tmp_path)
    if defect == 'binding_hash':
        report['plan_binding']['binding_sha256'] = '0' * 64
    elif defect == 'changed_rule_price':
        plan = deepcopy(report['plan_binding']['plan'])
        plan['entry_trigger_price'] = '14'
        plan['levels']['60m']['prior_max_high'] = '14'
        report['plan_binding'] = bind_quote_plan(plan, symbol='600519', now=BOUND_AT)
    elif defect in {'prior_source', 'current_source'}:
        case = prior if defect == 'prior_source' else current
        path = tmp_path / case['source_bindings']['15m']['path']
        path.write_bytes(path.read_bytes() + b' ')
    else:
        path = tmp_path / 'config/current-price-conditions.json'
        if defect == 'missing_registry':
            path.unlink()
        else:
            value = json.loads(path.read_bytes())
            value['items'].append(deepcopy(value['items'][0]))
            path.write_text(json.dumps(value), encoding='utf-8')
    before = files(tmp_path)
    result = project(tmp_path, report)
    assert result['status'] == 'UNASSESSABLE'
    expected = {'binding_hash': 'PRIOR_PLAN_BINDING_INVALID',
                'changed_rule_price': 'PRIOR_PLAN_RULE_OR_PRICE_DIFFERS_FROM_BOUND_SOURCE',
                'prior_source': 'PRIOR_PLAN_SOURCE_UNAVAILABLE_OR_INVALID_AT_BOUND_AT'}
    assert result['reason'] == expected.get(defect, 'CURRENT_COMPLETE_CASE_NOT_UNIQUELY_AVAILABLE')
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert files(tmp_path) == before


def test_binding_on_target_day_not_laundered_with_earlier_source_availability(tmp_path):
    target_morning = OBSERVE.replace(hour=10)
    report, _, _ = fixture(tmp_path, bound_at=target_morning)
    result = project(tmp_path, report)
    assert result['status'] == 'UNASSESSABLE'
    assert result['reason'] == 'PLAN_NOT_BOUND_BEFORE_TARGET_SESSION'
    assert result['bound_at'] == report['plan_binding']['bound_at']


def test_old_expiry_does_not_move_to_later_session(tmp_path):
    later = OBSERVE.replace(day=29)
    report, _, _ = fixture(tmp_path, observed_at=later)
    result = project(tmp_path, report, later)
    assert result['status'] == 'UNASSESSABLE'
    assert result['reason'] == 'TARGET_IS_NOT_THE_SEALED_NEXT_EXCHANGE_SESSION'


def test_resigned_binding_cannot_backdate_actual_source_acquisition(tmp_path):
    report, _, _ = fixture(tmp_path)
    earlier = BOUND_AT - timedelta(minutes=1)
    plan = deepcopy(report['plan_binding']['plan'])
    plan['data_available_at'] = earlier.isoformat()
    report['plan_binding'] = bind_quote_plan(plan, symbol='600519', now=earlier)
    result = project(tmp_path, report)
    assert result['status'] == 'UNASSESSABLE'
    assert result['reason'] == 'PRIOR_PLAN_SOURCE_UNAVAILABLE_OR_INVALID_AT_BOUND_AT'


def test_rehashed_incomplete_15m_is_rejected_by_native_loader(tmp_path):
    from value_investment_agent.infrastructure.hotspot.sina_price_case import decode_klines
    from value_investment_agent.infrastructure.hotspot.current_price_case import load_current_price_case
    report, _, current = fixture(tmp_path)
    raw_path = tmp_path / current['source_bindings']['15m']['path']
    rows = decode_klines(raw_path.read_bytes())
    rows.pop(-2)
    raw_path.write_bytes(('=(' + json.dumps(rows) + ');').encode())
    case_path = tmp_path / current['case_path']
    stored = json.loads(case_path.read_bytes())
    stored['source_bindings']['15m']['sha256'] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    case_path.write_text(json.dumps(stored), encoding='utf-8')
    registry_path = tmp_path / 'config/current-price-conditions.json'
    registry = json.loads(registry_path.read_bytes())
    digest = hashlib.sha256(case_path.read_bytes()).hexdigest()
    registry['items'][0]['case_sha256'] = digest
    registry_path.write_text(json.dumps(registry), encoding='utf-8')
    with pytest.raises(ValueError, match='Incomplete 15m session'):
        load_current_price_case(root=tmp_path, symbol='600519', case_path=case_path,
                                expected_sha256=digest, now=OBSERVE)
    before = files(tmp_path)
    result = project(tmp_path, report)
    assert result['status'] == 'UNASSESSABLE'
    assert result['reason'] == 'CURRENT_COMPLETE_CASE_NOT_UNIQUELY_AVAILABLE'
    assert files(tmp_path) == before


def test_projection_does_not_rewrite_original_completed_result_or_notifications(tmp_path):
    from value_investment_agent.application.hotspot.intraday_plan_observation import evaluate_quote_plan
    from value_investment_agent.application.hotspot.intraday_completed_plan import project_completed_plan
    from value_investment_agent.application.hotspot.public_condition_notifications import project_notification_inbox
    report, _, _ = fixture(tmp_path)
    identity = str(uuid4())
    completed = project_completed_plan(report['plan_binding'], {}, now=OBSERVE, include_documents=False)
    sample = dict(sample_id=identity, symbol='600519', checked_at=OBSERVE.astimezone(
        timezone.utc).isoformat(), status='STALE_OR_UNAVAILABLE',
        reason='COLLECTION_OR_EVIDENCE_FAILED', source_refs=[],
        condition_result=evaluate_quote_plan(report['plan_binding'], None, previous=None, now=OBSERVE),
        bar_bindings={}, bar_collection_status='UNAVAILABLE', completed_plan_result=completed)
    report['samples'] = [sample]
    report['bindings'] = [dict(sample_id=identity, sha256=None)]
    original = deepcopy(report)
    session = service.PublicObservationSession(tmp_path, clock=lambda: OBSERVE)
    session.directory.mkdir(parents=True)
    session._current = report
    session._persist()
    before = files(tmp_path)
    pointer = json.loads((session.directory / 'current.json').read_bytes())
    expected_inbox = project_notification_inbox([json.loads(service._bytes(original))], now=OBSERVE,
        snapshot_sha256=service._sha(service._bytes(pointer)))
    result = session.read()
    assert result['sealed_condition_path']['status'] == 'NOT_TRIGGERED'
    assert result['completed_plan_observation']['result_sha256'] == completed['result_sha256']
    assert result['completed_plan_observation']['status'] == completed['status']
    assert result['samples'][0]['completed_plan_result'] == completed
    assert result['notification_inbox'] == expected_inbox
    assert report == original and files(tmp_path) == before
