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
        marketwide_screen=dict(status='RESEARCH_ONLY', manifest_path=binding['path'],
            manifest_sha256=binding['sha256']))), encoding='utf-8')
    def replay(**kwargs):
        assert kwargs == dict(root=tmp_path.resolve(), manifest_binding=binding, now=NOW, limit=20)
        return dict(action='no_order', status='TEST_DELEGATED')
    monkeypatch.setattr(app, 'select_value_candidates', replay)
    assert app.select_current_value_candidates(root=tmp_path, now=NOW, limit=20)['status'] == 'TEST_DELEGATED'


LIVE = Path('D:/GPTProject/value-investment/.tmp/dual1')


@pytest.fixture(scope='module')
def real_replay():
    if not (LIVE / '.tmp/daily-workbench-latest-run.json').is_file():
        pytest.skip('retained public sources unavailable; synthetic unit tests remain offline')
    return app.select_current_value_candidates(root=LIVE, now=NOW)


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
    result = app.select_current_value_candidates(root=LIVE,
        now=datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert result['data_status'] == 'SOURCE_REVALIDATION_FAILED'
    assert result['shortlist'] == []


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
def source_package(tmp_path):
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
    files = {key: write(key + '.json', value) for key, value in payloads.items()}
    clock = datetime(2026, 9, 23, 8, tzinfo=timezone.utc)
    refs = {key: EvidenceReference(id=key, path=value['path'], sha256=value['sha256'],
        source_name=key, source_url='https://example.test/' + key, fetched_at=clock)
        for key, value in files.items()}
    receipt = build_discovery_receipt(run_id='test', generated_at=clock,
        official_payload=payloads['official'], tencent_payload=payloads['tencent'],
        sina_payload=payloads['sina'], dividend_payload=payloads['dividend'],
        financial_points=[], quote_date='2026-09-23', run_refs=refs)
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
