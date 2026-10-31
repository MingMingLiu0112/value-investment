"""Observation ordering must not mutate verified facts or trade eligibility."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.application.discovery import value_candidate_selection as app
from value_investment_agent.domain.discovery.value_candidate_selection import (
    CRITERIA, fingerprint, observation_conditions, rank_research_candidates,
)

NOW = datetime(2026, 10, 23, 8, tzinfo=timezone.utc)


def _points(**changes):
    values = ['18', '30', '8', '10']
    result = [dict(field_name=field, unit=unit, value=value, period_label='2025-12-31',
        available_at='2026-10-22T08:00:00+00:00', source_url='https://example.test/annual',
        raw_file_hash='a' * 64, source_id='source', data_point_id=str(index),
        validation_status='unverified')
        for index, ((field, unit, _), value) in enumerate(zip(CRITERIA, values))]
    for point in result:
        point.update(changes)
    return result


def _row(symbol='600001', points=None, **changes):
    conditions, period = observation_conditions(_points() if points is None else points, now=NOW)
    return dict(symbol=symbol, conditions=conditions, period=period,
        profile_status='GENERAL_RESEARCH', channels=[], **changes)


def test_observations_are_usable_without_promotion_or_mutation():
    points = _points()
    before = deepcopy(points)
    rows, queue = rank_research_candidates([_row(points=points)], limit=30)
    assert points == before
    assert queue[0]['observation_summary']['favorable'] == 4
    assert all(c['status'] == 'observed' and c['formal_fact'] is False for c in rows[0]['conditions'])
    assert not rows[0]['formal_eligibility'] and not rows[0]['buy_eligible']
    assert rows[0]['action'] == 'no_order'


def test_missing_is_not_zero_and_cannot_get_favorable_rank():
    rows, queue = rank_research_candidates([_row(points=[])], limit=30)
    assert not queue
    assert all(c['value'] is None and c['favorable'] is None for c in rows[0]['conditions'])
    assert rows[0]['observation_summary']['missing'] == 4


@pytest.mark.parametrize('mutation', [
    dict(value='NaN'), dict(value=True), dict(unit='ratio'),
    dict(available_at='2026-10-24T08:00:00+00:00'), dict(available_at='2026-10-22'),
    dict(raw_file_hash=None), dict(source_url=None), dict(available_at='2025-12-31T08:00:00+00:00'),
])
def test_bad_observation_is_conflicting_and_cannot_enter_queue(mutation):
    rows, queue = rank_research_candidates([_row(points=_points(**mutation))], limit=30)
    assert not queue
    assert rows[0]['observation_summary']['conflicting'] == 4


def test_duplicate_disagreement_not_last_write_wins():
    points = _points()
    points.append(dict(points[0], value='1'))
    conditions, _ = observation_conditions(points, now=NOW)
    assert conditions[0]['status'] == 'conflicting'
    assert conditions[0]['value'] is None


def test_exact_duplicate_is_not_new_evidence_strength():
    points = _points()
    conditions, _ = observation_conditions(points + deepcopy(points), now=NOW)
    assert len(conditions) == 4
    assert sum(c['favorable'] is True for c in conditions) == 4


def test_no_mixed_period_backfill():
    points = _points()
    points[0]['period_label'] = '2024-12-31'
    conditions, period = observation_conditions(points, now=NOW)
    assert period == '2025-12-31'
    assert conditions[0]['status'] == 'missing'


def test_stale_annual_not_current_priority():
    _, queue = rank_research_candidates([_row(points=_points(period_label='2024-12-31'))], limit=30)
    assert not queue


@pytest.mark.parametrize('flag', ['risk_warning', 'price_conflict'])
def test_risk_and_source_conflict_have_priority_over_favorable_data(flag):
    _, queue = rank_research_candidates([_row(**{flag: True})], limit=30)
    assert not queue


def test_specialized_profile_cannot_use_general_queue():
    row = _row()
    row['profile_status'] = 'SPECIALIZED_RESEARCH_REQUIRED'
    assert rank_research_candidates([row], limit=30)[1] == []


def test_financial_observations_order_before_pe_channel_count():
    good = _row('600002')
    poor = _row('600001', points=_points(value='-1'))
    poor['channels'] = ['value', 'cyclical', 'dividend_cash_return']
    rows, _ = rank_research_candidates([poor, good], limit=1)
    assert rows[0]['symbol'] == '600002'


@pytest.mark.parametrize('limit', [0, -1, 201, True, 1.5])
def test_invalid_budget(limit):
    with pytest.raises(ValueError):
        rank_research_candidates([], limit=limit)


def test_determinism_and_json_safe():
    first = rank_research_candidates([_row('600002'), _row('600001')], limit=1)
    second = rank_research_candidates([_row('600001'), _row('600002')], limit=1)
    assert fingerprint(first) == fingerprint(second)
    json.dumps(first, allow_nan=False)


def test_current_entry_fail_closed_without_runtime(tmp_path):
    result = app.select_current_value_candidates(root=tmp_path, now=NOW)
    assert result['data_status'] == 'SOURCE_REVALIDATION_FAILED'
    assert result['shortlist'] == [] and result['action'] == 'no_order'


def test_manifest_hash_and_path_fail_closed(tmp_path):
    base = tmp_path / 'runtime/daily-marketwide/test'
    base.mkdir(parents=True)
    path = base / 'manifest.json'
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        app.select_value_candidates(root=tmp_path,
            manifest_binding=dict(path=path.relative_to(tmp_path).as_posix(), sha256='a' * 64), now=NOW)
    with pytest.raises(ValueError):
        app.select_value_candidates(root=tmp_path,
            manifest_binding=dict(path='../escape.json', sha256='a' * 64), now=NOW)


def test_current_entry_delegates_exact_binding(tmp_path, monkeypatch):
    base = tmp_path / '.tmp'
    base.mkdir()
    binding = dict(path='runtime/daily-marketwide/test/manifest.json', sha256='a' * 64)
    (base / 'daily-workbench-latest-run.json').write_text(json.dumps(dict(
        schema_version='daily-workbench-run-v1', action='no_order', mode='SAFE_REFRESH',
        started_at='2026-10-23T07:00:00+00:00', finished_at='2026-10-23T07:01:00+00:00',
        marketwide_screen=dict(status='RESEARCH_ONLY', manifest_path=binding['path'],
            manifest_sha256=binding['sha256'], output_dir='runtime/daily-marketwide/test'))), encoding='utf-8')
    def replay(**kwargs):
        assert kwargs == dict(root=tmp_path.resolve(), manifest_binding=binding, now=NOW, limit=20)
        return dict(action='no_order', status='TEST_DELEGATED', available_at='2026-10-23T07:00:30+00:00')
    monkeypatch.setattr(app, 'select_value_candidates', replay)
    assert app.select_current_value_candidates(root=tmp_path, now=NOW, limit=20)['status'] == 'TEST_DELEGATED'


def _run_pointer(root, binding, *, mode='SAFE_REFRESH', current=False, **changes):
    screen = dict(status='RESEARCH_ONLY', manifest_path=binding['path'], manifest_sha256=binding['sha256'],
                  output_dir=binding['path'].rsplit('/', 1)[0])
    run = dict(schema_version='daily-workbench-run-v1', action='no_order', mode=mode,
        status='PARTIAL', started_at='2026-10-23T07:00:00+00:00',
        finished_at='2026-10-23T07:01:00+00:00',
        marketwide_screen=screen if current else dict(status='BLOCKED'),
        retained_marketwide_screen=screen, **changes)
    path = root / '.tmp/daily-workbench-latest-run.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(run), encoding='utf-8')
    return path, run


@pytest.mark.parametrize('mode,expected', [('SAFE_REFRESH', 'COLLECTION_FAILED'), ('READ_ONLY', 'NOT_ATTEMPTED')])
def test_failed_attempt_retains_exact_dated_research_with_original_times(source_package, mode, expected):
    root, binding, _, _ = source_package
    direct = app.select_value_candidates(root=root, manifest_binding=binding, now=NOW)
    path, run = _run_pointer(root, binding, mode=mode)
    before = path.read_bytes()
    result = app.select_current_value_candidates(root=root, now=NOW)
    assert result['items'] == direct['items']
    assert result['as_of'] == direct['as_of']
    assert result['available_at'] == direct['available_at']
    assert result['quote_date'] == direct['quote_date']
    assert result['snapshot_status'] == 'RETAINED_DATED_RESEARCH'
    assert result['refresh_status'] == expected
    assert result['latest_attempt']['status'] == 'BLOCKED'
    assert result['latest_attempt']['finished_at'] == run['finished_at']
    assert result['formal_eligibility'] is False and result['buy_eligible'] is False
    assert result['source_bindings'][-1]['sha256'] == hashlib.sha256(before).hexdigest()
    assert result['selection_sha256'] == fingerprint({k: v for k, v in result.items() if k != 'selection_sha256'})
    assert path.read_bytes() == before


def test_current_corrupt_manifest_must_not_fall_back_to_valid_retained_binding(source_package):
    root, binding, _, _ = source_package
    path, run = _run_pointer(root, binding, current=True)
    run['marketwide_screen'] = dict(run['marketwide_screen'], manifest_sha256='f' * 64)
    path.write_text(json.dumps(run), encoding='utf-8')
    result = app.select_current_value_candidates(root=root, now=NOW)
    assert result['data_status'] == 'SOURCE_REVALIDATION_FAILED' and result['items'] == []


def test_unfinished_attempt_is_not_called_failed_or_fresh(source_package):
    root, binding, _, _ = source_package
    path, run = _run_pointer(root, binding)
    run['finished_at'] = None
    path.write_text(json.dumps(run), encoding='utf-8')
    result = app.select_current_value_candidates(root=root, now=NOW)
    assert result['snapshot_status'] == 'RETAINED_DATED_RESEARCH'
    assert result['refresh_status'] == 'INCOMPLETE'
    assert result['input_sha256'] == fingerprint(result['source_bindings'])


@pytest.mark.parametrize('fault', ['old_receipt', 'missing_start', 'missing_finish', 'inverted', 'different_output'])
def test_current_label_requires_coherent_attempt_identity(source_package, fault):
    root, binding, _, _ = source_package
    path, run = _run_pointer(root, binding, current=True)
    run.update(started_at='2026-09-23T07:00:00+00:00', finished_at='2026-09-23T09:00:00+00:00')
    if fault == 'old_receipt':
        run.update(started_at='2026-10-23T07:00:00+00:00', finished_at='2026-10-23T09:00:00+00:00')
    elif fault == 'missing_start':
        run.pop('started_at')
    elif fault == 'missing_finish':
        run['finished_at'] = None
    elif fault == 'inverted':
        run['finished_at'] = '2026-09-23T06:00:00+00:00'
    else:
        run['marketwide_screen']['output_dir'] = 'runtime/daily-marketwide/another'
    path.write_text(json.dumps(run), encoding='utf-8')
    assert app.select_current_value_candidates(root=root, now=NOW)['data_status'] == 'SOURCE_REVALIDATION_FAILED'


def test_current_completed_attempt_has_its_own_source_generation(source_package):
    root, binding, _, _ = source_package
    path, run = _run_pointer(root, binding, current=True)
    run.update(started_at='2026-09-23T07:00:00+00:00', finished_at='2026-09-23T09:00:00+00:00')
    path.write_text(json.dumps(run), encoding='utf-8')
    result = app.select_current_value_candidates(root=root, now=NOW)
    assert result['snapshot_status'] == 'CURRENT_ATTEMPT_SOURCE_REVALIDATED'
    assert result['refresh_status'] == 'SOURCE_REVALIDATED'


@pytest.mark.parametrize('damage', ['tamper', 'missing', 'no_binding', 'future_attempt', 'future_source', 'wrong_policy'])
def test_retained_binding_revalidates_all_sources_and_time(source_package, damage):
    root, binding, manifest, write = source_package
    path, run = _run_pointer(root, binding)
    cutoff = NOW
    if damage == 'tamper':
        raw = root / manifest['files']['official']['path']
        raw.write_bytes(raw.read_bytes() + b' ')
    elif damage == 'missing':
        (root / manifest['files']['financial']['path']).unlink()
    elif damage == 'no_binding':
        run.pop('retained_marketwide_screen')
    elif damage == 'future_attempt':
        run['finished_at'] = '2026-10-24T08:00:00+00:00'
    elif damage == 'future_source':
        cutoff = datetime(2026, 9, 22, tzinfo=timezone.utc)
        run.pop('started_at')
        run.pop('finished_at')
    elif damage == 'wrong_policy':
        manifest['files']['policy'] = write('new-policy.json', dict(value_max_pe='1000'))
        changed = write('manifest.json', manifest)
        run['retained_marketwide_screen']['manifest_sha256'] = changed['sha256']
    path.write_text(json.dumps(run), encoding='utf-8')
    assert app.select_current_value_candidates(root=root, now=cutoff)['data_status'] == 'SOURCE_REVALIDATION_FAILED'


def test_pointer_race_is_not_published_as_a_stable_selection(source_package, monkeypatch):
    root, binding, _, _ = source_package
    path, _ = _run_pointer(root, binding)
    replay = app.select_value_candidates
    def changed(**kwargs):
        result = replay(**kwargs)
        path.write_bytes(path.read_bytes() + b' ')
        return result
    monkeypatch.setattr(app, 'select_value_candidates', changed)
    assert app.select_current_value_candidates(root=root, now=NOW)['data_status'] == 'SOURCE_REVALIDATION_FAILED'


LIVE = Path('D:/GPTProject/value-investment/.tmp/dual1')
REAL_MANIFEST = dict(path='runtime/daily-marketwide/20261022T1443164468299Z/manifest.json',
    sha256='719eb923b09a4298e568ff81d0ae00502251873a5a48332cf861f7495e7980ed')


@pytest.fixture(scope='module')
def real_replay():
    path = LIVE / REAL_MANIFEST['path']
    if not path.is_file():
        pytest.skip('retained public sources unavailable; synthetic unit tests remain offline')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == REAL_MANIFEST['sha256']
    return app.select_value_candidates(root=LIVE, manifest_binding=REAL_MANIFEST, now=NOW)


def test_real_cross_industry_replay(real_replay):
    result = real_replay
    assert result['data_status'] == 'PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS'
    assert result['coverage']['universe_count'] > 5000
    assert result['coverage']['observation_company_count'] > 5000
    assert len({row['industry'] for row in result['shortlist']}) >= 3
    assert len(result['shortlist']) == 30
    assert result['coverage']['official_fact_admission_count'] == 0
    assert all(row['buy_eligible'] is False for row in result['items'])
    bank = next(row for row in result['items'] if row['symbol'] == '000001')
    assert bank['profile_status'] == 'SPECIALIZED_RESEARCH_REQUIRED'
    assert not bank['research_priority_eligible']
    assert all(c['favorable'] is None for c in bank['conditions'])


def test_real_future_cutoff_is_not_pit_backfill(real_replay):
    with pytest.raises(ValueError, match='not available at cutoff'):
        app.select_value_candidates(root=LIVE, manifest_binding=REAL_MANIFEST,
            now=datetime(2026, 10, 21, tzinfo=timezone.utc))


def test_real_fingerprint_and_explainability(real_replay):
    result = real_replay
    assert len(result['selection_sha256']) == 64
    assert result['parameter_sha256'] == fingerprint(result['parameters'])
    assert all(row['conditions'] and row['blockers'] and row['rationale'] for row in result['shortlist'])
    assert all(c['evidence'] for row in result['shortlist'] for c in row['conditions'] if c['status'] == 'observed')


def test_naive_cutoff_rejected():
    with pytest.raises(ValueError, match='timezone'):
        observation_conditions(_points(), now=NOW.replace(tzinfo=None))


@pytest.fixture
def source_package(tmp_path, request):
    from test_m2_opportunity_discovery import (
        _official_payload, _tencent_payload, _sina_payload, _dividend_payload,
    )
    from value_investment_agent.m2_discovery_engine import M2ScreeningPolicy, build_discovery_receipt
    from value_investment_agent.m2_opportunity_discovery import EvidenceReference
    from value_investment_agent.application.product.value_discovery_surface import project_value_discovery_report

    directory = tmp_path / 'runtime/daily-marketwide/test'
    directory.mkdir(parents=True)
    def write(name, value):
        path = directory / name
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        path.write_bytes(raw)
        return dict(path=path.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(raw).hexdigest())
    payloads = dict(official=_official_payload(), tencent=_tencent_payload(),
                    sina=_sina_payload(), dividend=_dividend_payload(), financial=dict(points=[]))
    if hasattr(request, 'param') and isinstance(request.param, dict):
        from value_investment_agent.infrastructure.screening.evidence_screen_v3 import build_discovery_receipt
        options = request.param
        symbols = [str(600001 + index) for index in range(options['count'])]
        target = symbols[0] if len(symbols) == 4 else symbols[-1]
        payloads['official']['records'] = [dict(payloads['official']['records'][0], symbol=s) for s in symbols]
        payloads['tencent']['rows'] = [dict(payloads['tencent']['rows'][0], code='sh' + s,
            pe_ttm='30' if s == target and not options['pass_channel'] else '10') for s in symbols]
        payloads['sina']['rows'] = [dict(payloads['sina']['rows'][0], code=s,
            per='30' if s == target and not options['pass_channel'] else '10',
            trade='30' if options['conflict'] and s == target else '20') for s in symbols]
        payloads['financial']['points'] = [dict(point, symbol=target) for point in
            _points(available_at='2026-09-22T08:00:00+00:00')]
    elif hasattr(request, 'param'):
        # Exercise the default policy's real 50-row budget without changing thresholds.
        symbols = [str(600001 + index) for index in range(51)]
        payloads['official']['records'] = [dict(payloads['official']['records'][0], symbol=s) for s in symbols]
        payloads['tencent']['rows'] = [dict(payloads['tencent']['rows'][0], code='sh' + s) for s in symbols]
        payloads['sina']['rows'] = [dict(payloads['sina']['rows'][0], code=s,
            trade='30' if request.param and s == symbols[-1] else '20') for s in symbols]
    files = {key: write(key + '.json', value) for key, value in payloads.items()}
    clock = datetime(2026, 9, 23, 8, tzinfo=timezone.utc)
    refs = {key: EvidenceReference(id=key, path=value['path'], sha256=value['sha256'],
        source_name=key, source_url='https://example.test/' + key, fetched_at=clock)
        for key, value in files.items()}
    receipt = build_discovery_receipt(run_id='test', generated_at=clock,
        official_payload=payloads['official'], tencent_payload=payloads['tencent'],
        sina_payload=payloads['sina'], dividend_payload=payloads['dividend'],
        financial_points=payloads['financial']['points'], quote_date='2026-09-23', run_refs=refs)
    files['receipt'] = write('receipt.json', receipt.as_policy())
    files['policy'] = write('policy.json', M2ScreeningPolicy().as_policy())
    report = project_value_discovery_report(root=tmp_path,
        receipt_path=tmp_path / files['receipt']['path'], receipt_sha256=files['receipt']['sha256'])
    files['lead_report'] = write('report.json', report)
    summary = dict(action='no_order', as_of=report['as_of'], channel_counts=report['channel_counts'],
                   data_health=report['data_health'])
    manifest = dict(schema_version='m2-run-manifest-v1', files=files, summary=summary)
    binding = write('manifest.json', manifest)
    return tmp_path, binding, manifest, write


def test_offline_full_source_package(source_package):
    root, binding, _, _ = source_package
    result = app.select_value_candidates(root=root, manifest_binding=binding, now=NOW)
    assert result['coverage']['universe_count'] == 4
    assert result['coverage']['observation_company_count'] == 0
    assert result['coverage']['specialized_count'] == 1
    assert all(row['financial_quality_status'] == 'NOT_GRANTED_BY_OBSERVATION_RANKING'
               for row in result['items'])


@pytest.mark.parametrize('source', ['official', 'tencent', 'sina', 'dividend', 'financial', 'receipt', 'lead_report', 'policy'])
def test_every_bound_file_tamper_rejected(source_package, source):
    root, binding, manifest, _ = source_package
    path = root / manifest['files'][source]['path']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError):
        app.select_value_candidates(root=root, manifest_binding=binding, now=NOW)


def test_financial_file_cannot_be_rebound_outside_consumed_receipt(source_package):
    root, _, manifest, write = source_package
    manifest['files']['financial'] = write('different-financial.json', dict(points=[dict(symbol='600001')]))
    binding = write('manifest.json', manifest)
    with pytest.raises(ValueError, match='not consumed'):
        app.select_value_candidates(root=root, manifest_binding=binding, now=NOW)


def test_unknown_policy_cannot_silently_change_queue(source_package):
    root, _, manifest, write = source_package
    manifest['files']['policy'] = write('new-policy.json', dict(value_max_pe='1000'))
    binding = write('manifest.json', manifest)
    with pytest.raises(ValueError, match='unrecognized M2 policy'):
        app.select_value_candidates(root=root, manifest_binding=binding, now=NOW)


@pytest.mark.parametrize('source_package', [False, True], indirect=True)
def test_budget_quote_conflict_through_source_replay_and_research_queue(source_package):
    root, binding, manifest, _ = source_package
    receipt = json.loads((root / manifest['files']['receipt']['path']).read_text(encoding='utf-8'))
    evaluation = next(row for row in receipt['channel_results']['value']['evaluations']
                      if row['symbol'] == '600051')
    conflict = evaluation['status'] == 'CONFLICT'
    # The bound raw source, rather than the status being tested, owns this expectation.
    source = json.loads((root / manifest['files']['sina']['path']).read_text(encoding='utf-8'))
    expected_conflict = source['rows'][-1]['trade'] == '30'
    assert conflict == expected_conflict
    assert evaluation['status'] == ('CONFLICT' if expected_conflict else 'BUDGET_EXCLUDED')
    result = app.select_value_candidates(root=root, manifest_binding=binding, now=NOW, limit=200)
    row = next(row for row in result['items'] if row['symbol'] == '600051')
    assert row['price_conflict'] == expected_conflict
    assert row['research_priority_eligible'] == (not expected_conflict)
    assert ('600051' in {item['symbol'] for item in result['shortlist']}) == (not expected_conflict)
    assert result['coverage']['research_queue_count'] == (50 if expected_conflict else 51)
    assert row['action'] == result['action'] == 'no_order'
    assert not row['formal_eligibility'] and not row['buy_eligible']


@pytest.mark.parametrize('source_package', [
    dict(count=count, pass_channel=passed, conflict=conflict)
    for count in (4, 51) for passed in (False, True) for conflict in (False, True)
], indirect=True)
def test_raw_quote_conflict_survives_nonpassing_channels_through_selector_and_api(source_package, monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.application.hotspot import candidate_selection as hotspot

    root, binding, manifest, _ = source_package
    raw = json.loads((root / manifest['files']['sina']['path']).read_bytes())
    target = '600001' if len(raw['rows']) == 4 else '600051'
    original = next(row for row in raw['rows'] if row['code'] == target)
    conflict, passed = original['trade'] == '30', original['per'] == '10'
    receipt = json.loads((root / manifest['files']['receipt']['path']).read_bytes())
    assert receipt['rule_version'] == 'm2-evidence-screen-v3'
    assert receipt['data_health']['price_conflict_count'] == int(conflict)
    statuses = {channel: next(row['status'] for row in data['evaluations'] if row['symbol'] == target)
                for channel, data in receipt['channel_results'].items()}
    if not passed:
        assert statuses == dict(quality='DATA_GAP', dividend_cash_return='NOT_EVALUATED',
                                value='REJECTED', cyclical='NOT_EVALUATED')
    result = app.select_value_candidates(root=root, manifest_binding=binding, now=NOW, limit=200)
    row = next(row for row in result['items'] if row['symbol'] == target)
    assert row['observation_summary']['favorable'] == 4
    assert all(not other['price_conflict'] and other['research_priority_eligible']
               for other in result['items'] if other['symbol'] != target)
    assert result['coverage']['research_queue_count'] == len(raw['rows']) - int(conflict)
    assert row['price_conflict'] is conflict
    assert row['research_priority_eligible'] is (not conflict)
    assert (target in {item['symbol'] for item in result['shortlist']}) is (not conflict)
    assert not row['formal_eligibility'] and not row['buy_eligible']
    _run_pointer(root, binding)
    # Only the unrelated hotspot lane is stubbed; value sources, selector and route are real.
    monkeypatch.setattr(hotspot, 'select_current_hotspot_candidates',
        lambda **kwargs: dict(action='no_order', items=[], shortlist=[]))
    response = TestClient(create_app(root)).get('/api/v1/strategy-selection', params={'q_value': target})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    payload = response.json()
    value = payload['value']
    assert value['data_status'] == 'PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS'
    assert value['coverage']['universe_count'] == len(raw['rows'])
    assert value['pagination']['total'] == int(not conflict)
    assert [item['symbol'] for item in value['items']] == ([] if conflict else [target])
    assert [item['symbol'] for item in value['shortlist']] == ([] if conflict else [target])
    assert payload['action'] == value['action'] == 'no_order'
    assert not payload['formal_eligibility'] and not payload['trade_eligible']


@pytest.mark.parametrize('source', ['tencent', 'sina'])
def test_quote_replay_rejects_manifest_source_not_consumed_by_receipt(source_package, source):
    root, _, manifest, write = source_package
    payload = json.loads((root / manifest['files'][source]['path']).read_bytes())
    manifest['files'][source] = write('rebound-' + source + '.json', payload)
    binding = write('manifest.json', manifest)
    with pytest.raises(ValueError, match='not consumed by M2 receipt'):
        app.select_value_candidates(root=root, manifest_binding=binding, now=NOW)
